#include "DEV_Config.h"
#include "AMOLED_1in8.h"
#include "qspi_pio.h"
#include "QMI8658.h"
#include "FT3168.h"
#include "es8311.h"
#include "build/pets/zundamon/generated/pet_images.h"
#include "GUI_Paint.h"
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"

pet_image_t const *PIC;
int flag_click = 0,flag_dclick = 0;
uint8_t i2c_lock = 0;
pet_state_t working_state = 0;
#define I2C_LOCK() i2c_lock = 1
#define I2C_UNLOCK() i2c_lock = 0

UWORD BlackImage[AMOLED_1IN8_HEIGHT*AMOLED_1IN8_WIDTH];

void Touch_INT_callback(uint gpio, uint32_t events);

int main() 
{
    stdio_init_all();

    char linebuf[128];
    int linepos = 0;

    if(DEV_Module_Init()!=0){
        return -1;
    }

    /*Audio Init*/
    printf("Audio initializing...\r\n");
    es8311_init(pico_audio);
    es8311_sample_frequency_config(pico_audio.mclk_freq, pico_audio.sample_freq);
    es8311_microphone_config();
    es8311_voice_volume_set(pico_audio.volume);
    es8311_microphone_gain_set(pico_audio.mic_gain);
    audio_loopback_start();

    uint16_t chip_id = es8311_read_id();
    printf("Chip ID:0x%x", chip_id);

    // PWR KEY
    DEV_IRQ_SET(SYS_OUT, GPIO_IRQ_LEVEL_HIGH, &Touch_INT_callback);
    
    /*QSPI PIO Init*/
    QSPI_GPIO_Init(qspi);
    QSPI_PIO_Init(qspi);
    QSPI_4Wrie_Mode(&qspi);

    /*AMOLED Init*/
    printf("1.8inch AMOLED initializing...\r\n");
    AMOLED_1IN8_Init();
    AMOLED_1IN8_SetBrightness(100);
    
    // UDOUBLE Imagesize = AMOLED_1IN8_HEIGHT*AMOLED_1IN8_WIDTH*2;
    // UWORD *BlackImage;
    // if((BlackImage = (UWORD *)malloc(Imagesize)) == NULL) {
    //     printf("Failed to apply for black memory...\r\n");
    //     exit(0);
    // }

    /* Create a new image cache named IMAGE_RGB and fill it with white*/
    Paint_NewImage((UBYTE *)BlackImage, AMOLED_1IN8.WIDTH, AMOLED_1IN8.HEIGHT, 0, WHITE);
    Paint_SetScale(65);
    Paint_SetRotate(ROTATE_0);
    Paint_Clear(BLACK);
    AMOLED_1IN8_Display(BlackImage);

    /* QMI8658 Init */
    float acc[3], gyro[3];
    unsigned int tim_count = 0;
    const float conversion_factor = 3.3f / (1 << 12) * 3;
    QMI8658_init();
    FT3168_Init(FT3168_Gesture_Mode);
    DEV_KEY_Config(Touch_INT_PIN);
    DEV_IRQ_SET(Touch_INT_PIN, GPIO_IRQ_EDGE_RISE, &Touch_INT_callback);

    /* Refresh the picture in RAM to LCD*/
    pet_state_t pre_state = PET_STATE_WAVING;
    pet_state_t state = PET_STATE_IDLE;
    working_state = PET_STATE_IDLE;
    int frame = 0;
    int frame_count = pet_state_frame_counts[0];
    absolute_time_t next_audio_process = make_timeout_time_ms(20);
    absolute_time_t next_frame_update = get_absolute_time();
    while(1)
    {
        while(1) {
            int c = getchar_timeout_us(0);
            if (c == PICO_ERROR_TIMEOUT || c == PICO_ERROR_NO_DATA)
                break;
            putchar(c); // エコーバック
            if (c == '\r' || c == '\n') {
                if (c == '\r')
                    putchar('\n');
                if (linepos > 0) {
                    linebuf[linepos] = '\0';
                    // ここでコマンド処理
                    if (strcmp(linebuf, "idle") == 0) {
                        working_state = PET_STATE_IDLE;
                    } else if (strcmp(linebuf, "failed") == 0) {
                        working_state = PET_STATE_FAILED;
                    } else if (strcmp(linebuf, "waiting") == 0) {
                        working_state = PET_STATE_WAITING;
                    } else if (strcmp(linebuf, "running") == 0) {
                        working_state = PET_STATE_RUNNING;
                    } else if (strcmp(linebuf, "review") == 0) {
                        working_state = PET_STATE_REVIEW;
                    } else if (strcmp(linebuf, "loopback") == 0) {
                        Loopback_test();
                    } else {
                        printf("Unknown command: %s\n", linebuf);
                    }
                    linepos = 0;
                }
            } else if (linepos < (int)sizeof(linebuf) - 1) {
                linebuf[linepos++] = (char)c;
            }
        }

        if (time_reached(next_audio_process)) {
            audio_loopback_process();
            next_audio_process = make_timeout_time_ms(20);
        }

        if (!time_reached(next_frame_update)) {
            sleep_ms(1);
            continue;
        }
        next_frame_update = make_timeout_time_ms(100);

        if (flag_click) {
            flag_click = 0;
            state = PET_STATE_JUMPING;
        }
        else if (flag_dclick) {
            flag_dclick = 0;
            state = PET_STATE_WAVING;
        }
        else if (state == working_state) {
            while(i2c_lock);
            I2C_LOCK();
            QMI8658_read_xyz(acc, gyro, &tim_count);
            I2C_UNLOCK();
            if (acc[1] > 200) {
                state = PET_STATE_RUNNING_RIGHT;
            }
            else if (acc[1] < -200) {
                state = PET_STATE_RUNNING_LEFT;
            }
            else {
                state = working_state;
            }
        }
        if (state != pre_state) {
            printf("State changed: %d -> %d\n", pre_state, state);
            pre_state = state;
            PIC = pet_state_frames[state];
            frame = 0;
            frame_count = pet_state_frame_counts[state];
        }
        Paint_DrawImage(PIC[frame].data, (AMOLED_1IN8.WIDTH - PET_IMAGE_WIDTH) / 2, (AMOLED_1IN8.HEIGHT - PET_IMAGE_HEIGHT) / 2, PET_IMAGE_WIDTH, PET_IMAGE_HEIGHT);
        AMOLED_1IN8_Display(BlackImage);
        frame++;
        if (frame >= frame_count) {
            state = working_state;
            frame = 0;
            frame_count = pet_state_frame_counts[state];
        }
    }

     /* Module Exit */
    //  free(BlackImage);
    //  BlackImage = NULL;
     
     DEV_Module_Exit();
}

void Touch_INT_callback(uint gpio, uint32_t events)
{
    if(i2c_lock)return;
    if (gpio == Touch_INT_PIN)
    {
        if(FT3168.mode != FT3168_Point_Mode)
        {
            uint8_t gesture = FT3168_Get_Gesture();

            if (gesture == FT3168_Gesture_Click)
            {
                flag_click = 1;
            }
            else if (gesture == FT3168_Gesture_Double_Click)
            {
                flag_dclick = 1;
            }
        }
        else
        {
            flag_click = 1;
        }
    }
    else if(gpio == SYS_OUT)
    {
        watchdog_reboot(0,0,0);
    }
}
