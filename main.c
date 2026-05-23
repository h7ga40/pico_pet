#include "DEV_Config.h"
#include "AMOLED_1in8.h"
#include "qspi_pio.h"
#include "QMI8658.h"
#include "FT3168.h"
#include "build/pets/zundamon/generated/pet_images.h"
#include "GUI_Paint.h"

pet_image_t const *PIC;
int flag=0;
uint8_t i2c_lock = 0;
#define I2C_LOCK() i2c_lock = 1
#define I2C_UNLOCK() i2c_lock = 0

void Touch_INT_callback(uint gpio, uint32_t events);

int main() 
{
    if(DEV_Module_Init()!=0){
        return -1;
    }

    // PWR KEY
    DEV_IRQ_SET(SYS_OUT, GPIO_IRQ_LEVEL_HIGH, &Touch_INT_callback);
    
    /*QSPI PIO Init*/
    QSPI_GPIO_Init(qspi);
    QSPI_PIO_Init(qspi);
    QSPI_4Wrie_Mode(&qspi);

    /*AMOLED Init*/
    printf("1.8inch AMOLED demo...\r\n");
    AMOLED_1IN8_Init();
    AMOLED_1IN8_SetBrightness(100);
    
    UDOUBLE Imagesize = AMOLED_1IN8_HEIGHT*AMOLED_1IN8_WIDTH*2;
    UWORD *BlackImage;
    if((BlackImage = (UWORD *)malloc(Imagesize)) == NULL) {
        printf("Failed to apply for black memory...\r\n");
        exit(0);
    }

    /*1.Create a new image cache named IMAGE_RGB and fill it with white*/
    Paint_NewImage((UBYTE *)BlackImage, AMOLED_1IN8.WIDTH, AMOLED_1IN8.HEIGHT, 0, WHITE);
    Paint_SetScale(65);
    Paint_SetRotate(ROTATE_0);
    Paint_Clear(BLACK);
    AMOLED_1IN8_Display(BlackImage);

    /* GUI */
    printf("drawing...\r\n");

    /* Refresh the picture in RAM to LCD*/
    pet_state_t state = PET_STATE_IDLE;
    while(1)
    {
        int frame_count = 0;
        switch(state)
        {
            case PET_STATE_IDLE:
                PIC = pet_idle_frames;
                frame_count = PET_IDLE_FRAME_COUNT;
                state = PET_STATE_RUNNING_RIGHT;
                break;
            case PET_STATE_RUNNING_RIGHT:
                PIC = pet_running_right_frames;
                frame_count = PET_RUNNING_RIGHT_FRAME_COUNT;
                state = PET_STATE_RUNNING_LEFT;
                break;
            case PET_STATE_RUNNING_LEFT:
                PIC = pet_running_left_frames;
                frame_count = PET_RUNNING_LEFT_FRAME_COUNT;
                state = PET_STATE_WAVING;
                break;
            case PET_STATE_WAVING:
                PIC = pet_waving_frames;
                frame_count = PET_WAVING_FRAME_COUNT;
                state = PET_STATE_JUMPING;
                break;
            case PET_STATE_JUMPING:
                PIC = pet_jumping_frames;
                frame_count = PET_JUMPING_FRAME_COUNT;
                state = PET_STATE_FAILED;
                break;
            case PET_STATE_FAILED:
                PIC = pet_failed_frames;
                frame_count = PET_FAILED_FRAME_COUNT;
                state = PET_STATE_WAITING;
                break;
            case PET_STATE_WAITING:
                PIC = pet_waiting_frames;
                frame_count = PET_WAITING_FRAME_COUNT;
                state = PET_STATE_RUNNING;
                break;
            case PET_STATE_RUNNING:
                PIC = pet_running_frames;
                frame_count = PET_RUNNING_FRAME_COUNT;
                state = PET_STATE_REVIEW;
                break;
            case PET_STATE_REVIEW:
                PIC = pet_review_frames;
                frame_count = PET_REVIEW_FRAME_COUNT;
                state = PET_STATE_IDLE;
                break;
            default:
                PIC = pet_idle_frames;
                frame_count = PET_IDLE_FRAME_COUNT;
                state = PET_STATE_IDLE;
                break;
        }
        for (int i = 0; i < frame_count; i++) {
            Paint_DrawImage(PIC[i].data, (AMOLED_1IN8.WIDTH - PET_IMAGE_WIDTH) / 2, (AMOLED_1IN8.HEIGHT - PET_IMAGE_HEIGHT) / 2, PET_IMAGE_WIDTH, PET_IMAGE_HEIGHT);
            AMOLED_1IN8_Display(BlackImage);
            DEV_Delay_ms(100);
        }
    }

     /* Module Exit */
     free(BlackImage);
     BlackImage = NULL;
     
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
                
            if (gesture == FT3168_Gesture_Double_Click)
            {
                flag = 1;
            }
        }
        else
        {
            flag = 1;
        }
    }
    else if(gpio == SYS_OUT)
    {
        watchdog_reboot(0,0,0);
    }
}
