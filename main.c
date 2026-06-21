#include "DEV_Config.h"
#include "AMOLED_1in8.h"
#include "qspi_pio.h"
#include "QMI8658.h"
#include "FT3168.h"
#include "es8311.h"
#include "build/pets/zundamon/generated/pet_images.h"
#include "wakeword.h"
#include "tts_phrase_pcm.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pico/stdio.h"
#include "pico/stdlib.h"

pet_image_t const *PIC;
int flag_click = 0,flag_dclick = 0;
uint8_t i2c_lock = 0;
pet_state_t working_state = 0;
#define I2C_LOCK() i2c_lock = 1
#define I2C_UNLOCK() i2c_lock = 0

static const uint16_t pet_frame_intervals_ms[PET_IMAGE_STATE_COUNT] = {
    [PET_STATE_IDLE] = 1000,
    [PET_STATE_RUNNING_RIGHT] = 100,
    [PET_STATE_RUNNING_LEFT] = 100,
    [PET_STATE_WAVING] = 100,
    [PET_STATE_JUMPING] = 100,
    [PET_STATE_FAILED] = 100,
    [PET_STATE_WAITING] = 100,
    [PET_STATE_RUNNING] = 100,
    [PET_STATE_REVIEW] = 100,
};
static const int16_t pet_image_offset_x = 0;
static const int16_t pet_image_offset_y = 0;

void Touch_INT_callback(uint gpio, uint32_t events);

static uint32_t tts_random_state;

#define PC_PLAY_SAMPLE_RATE 16000u
#define PC_PLAY_BLOCK_SAMPLES (PICO_SAMPLE_FREQ / 50)

typedef enum {
    SERIAL_COMMAND,
    SERIAL_PLAY_RECEIVING,
    SERIAL_PLAY_DRAINING,
} serial_audio_state_t;

static serial_audio_state_t serial_audio_state = SERIAL_COMMAND;
static int16_t pc_play_block[PC_PLAY_BLOCK_SAMPLES];
static size_t pc_play_block_samples;
static size_t pc_play_block_target;
static size_t pc_play_total_samples;
static size_t pc_play_received_samples;
static uint8_t pc_play_low_byte;
static bool pc_play_have_low_byte;
static bool pc_play_announced;

static bool play_random_tts(void)
{
    if (g_tts_pcm_phrase_count == 0 || audio_playback_is_busy())
        return false;

    if (tts_random_state == 0)
        tts_random_state = time_us_32() | 1u;
    tts_random_state ^= tts_random_state << 13;
    tts_random_state ^= tts_random_state >> 17;
    tts_random_state ^= tts_random_state << 5;

    size_t index = tts_random_state % g_tts_pcm_phrase_count;
    const tts_pcm_phrase_t *phrase = &g_tts_pcm_phrases[index];
    if (!audio_play_pcm16_start(phrase->samples, phrase->sample_count))
        return false;

    wakeword_set_debug_enabled(false);
    printf("TTS PCM playback: phrase=%u samples=%u at 16000 Hz\n",
           (unsigned)index, (unsigned)phrase->sample_count);
    return true;
}

static void stream_pcm_data(uint32_t seconds)
{
    const uint32_t sample_count = PICO_SAMPLE_FREQ * seconds;
    int16_t samples[PICO_SAMPLE_FREQ / 50];
    uint8_t bytes[(PICO_SAMPLE_FREQ / 50) * 2];
    uint32_t sent = 0;

    wakeword_set_debug_enabled(false);
    printf("PCM16 %lu %u\n", (unsigned long)sample_count, PICO_SAMPLE_FREQ);
    sleep_ms(100);

    while (sent < sample_count) {
        size_t count = audio_input_read_next(samples, PICO_SAMPLE_FREQ / 50);
        if (count == 0) {
            sleep_ms(1);
            continue;
        }
        if (count > sample_count - sent)
            count = sample_count - sent;

        for (size_t i = 0; i < count; ++i) {
            bytes[i * 2] = (uint8_t)(samples[i] & 0xff);
            bytes[i * 2 + 1] = (uint8_t)(((uint16_t)samples[i] >> 8) & 0xff);
        }
        stdio_put_string((const char *)bytes, (int)(count * 2), false, false);
        sent += (uint32_t)count;
    }

    printf("\nENDPCM\n");
    stdio_flush();
    wakeword_init();
}

bool tts_was_busy = false;

static void pc_play_request_next_block(void)
{
    pc_play_block_target = audio_play_stream_writable_samples();
    if (pc_play_block_target > 0) {
        printf("READY PLAY %u\n", (unsigned)pc_play_block_target);
    }
}

static void pc_play_accept_block(void)
{
    if (!audio_play_stream_write(pc_play_block, pc_play_block_samples)) {
        printf("ERROR playback buffer\n");
        return;
    }

    pc_play_received_samples += pc_play_block_samples;
    pc_play_block_samples = 0;
    if (!pc_play_announced) {
        pc_play_announced = true;
        printf("PLAYING\n");
    }

    if (pc_play_received_samples == pc_play_total_samples) {
        serial_audio_state = SERIAL_PLAY_DRAINING;
        printf("PLAY RECEIVED\n");
        return;
    }

    pc_play_request_next_block();
}

static void process_command(const char *linebuf)
{
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
    } else if (strcmp(linebuf, "mic") == 0) {
        int16_t samples[PICO_SAMPLE_FREQ / 50];
        size_t sample_count = audio_input_copy_latest(samples, PICO_SAMPLE_FREQ / 50);
        int32_t peak = 0;
        int64_t sum_squares = 0;
        for (size_t i = 0; i < sample_count; ++i) {
            int32_t sample = samples[i];
            int32_t magnitude = sample < 0 ? -sample : sample;
            if (magnitude > peak)
                peak = magnitude;
            sum_squares += (int64_t)sample * sample;
        }
        if (sample_count == 0) {
            printf("Mic: no new samples\n");
        } else {
            printf("Mic: samples=%u peak=%ld mean_square=%lld\n",
                    (unsigned)sample_count,
                    (long)peak,
                    sum_squares / (int64_t)sample_count);
        }
    } else if (strncmp(linebuf, "record ", 7) == 0) {
        uint32_t seconds = (uint32_t)strtoul(linebuf + 7, NULL, 10);
        if (seconds == 0)
            seconds = 1;
        else if (seconds > 10)
            seconds = 10;
        stream_pcm_data(seconds);
    } else if (strcmp(linebuf, "tts") == 0) {
        if (play_random_tts()) {
            tts_was_busy = true;
        } else {
            printf("TTS playback busy\n");
        }
    } else if (strncmp(linebuf, "play ", 5) == 0) {
        unsigned long sample_count;
        unsigned int sample_rate;
        if (sscanf(linebuf + 5, "%lu %u", &sample_count, &sample_rate) != 2 ||
            sample_count == 0 || sample_rate != PC_PLAY_SAMPLE_RATE ||
            !audio_play_stream_start(sample_count)) {
            printf("ERROR play expects: play <samples> 16000\n");
            return;
        }

        pc_play_total_samples = sample_count;
        pc_play_received_samples = 0;
        pc_play_block_samples = 0;
        pc_play_have_low_byte = false;
        pc_play_announced = false;
        serial_audio_state = SERIAL_PLAY_RECEIVING;
        pc_play_request_next_block();
    } else {
        printf("Unknown command: %s\n", linebuf);
    }
}

static void poll_serial_commands(void)
{
    static char linebuf[128];
    static int linepos = 0;

    if (serial_audio_state == SERIAL_PLAY_DRAINING) {
        if (!audio_playback_is_busy()) {
            serial_audio_state = SERIAL_COMMAND;
            printf("PLAY DONE\n");
        }
        return;
    }

    while(1) {
        if (serial_audio_state == SERIAL_PLAY_RECEIVING) {
            if (pc_play_block_target == 0) {
                pc_play_request_next_block();
                if (pc_play_block_target == 0)
                    break;
            }

            int c = getchar_timeout_us(0);
            if (c == PICO_ERROR_TIMEOUT || c == PICO_ERROR_NO_DATA)
                break;

            if (!pc_play_have_low_byte) {
                pc_play_low_byte = (uint8_t)c;
                pc_play_have_low_byte = true;
                continue;
            }

            pc_play_block[pc_play_block_samples++] =
                (int16_t)((uint16_t)pc_play_low_byte | ((uint16_t)(uint8_t)c << 8));
            pc_play_have_low_byte = false;
            if (pc_play_block_samples == pc_play_block_target)
                pc_play_accept_block();
            continue;
        }

        int c = getchar_timeout_us(0);
        if (c == PICO_ERROR_TIMEOUT || c == PICO_ERROR_NO_DATA)
            break;
        putchar(c); // エコーバック
        if (c == '\r' || c == '\n') {
            if (c == '\r')
                putchar('\n');
            if (linepos > 0) {
                linebuf[linepos] = '\0';
                process_command(linebuf);
                linepos = 0;
            }
        } else if (linepos < (int)sizeof(linebuf) - 1) {
            linebuf[linepos++] = (char)c;
        }
    }
}

int main() 
{
    stdio_init_all();

    if(DEV_Module_Init()!=0){
        return -1;
    }

    /*Audio Init*/
    printf("Audio initializing...\r\n");
    mclk_pio_init();
    es8311_init(pico_audio);
    es8311_sample_frequency_config(pico_audio.mclk_freq, pico_audio.sample_freq);
    es8311_microphone_config();
    es8311_voice_volume_set(pico_audio.volume);
    es8311_microphone_gain_set(pico_audio.mic_gain);
    audio_loopback_start();
    wakeword_init();

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

    /* The AMOLED retains its own framebuffer, so no MCU framebuffer is needed. */
    AMOLED_1IN8_Clear(0x0000);

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
    int frame_count = pet_state_frame_counts[state];
    absolute_time_t next_audio_process = make_timeout_time_ms(20);
    absolute_time_t next_state_update = get_absolute_time();
    absolute_time_t next_frame_update = get_absolute_time();
    while(1)
    {
        poll_serial_commands();

        if (time_reached(next_audio_process)) {
            int16_t wakeword_samples[PICO_SAMPLE_FREQ / 50];
            if (audio_playback_is_busy()) {
                if (serial_audio_state == SERIAL_COMMAND)
                    tts_was_busy = true;
            } else if (tts_was_busy) {
                tts_was_busy = false;
                wakeword_set_debug_enabled(true);
                state = working_state;
                printf("TTS playback complete\n");
            }

            size_t wakeword_sample_count;
            while ((wakeword_sample_count = audio_input_read_next(
                        wakeword_samples, PICO_SAMPLE_FREQ / 50)) > 0) {
                if (!audio_playback_is_busy() && !tts_was_busy &&
                    wakeword_process_frame(wakeword_samples, wakeword_sample_count)) {
                    printf("Wakeword event detected\n");
                    if (play_random_tts())
                        tts_was_busy = true;
                }
            }
            next_audio_process = make_timeout_time_ms(20);
        }

        if (audio_playback_is_busy() || tts_was_busy) {
            state = PET_STATE_WAVING;
        }
        else if (flag_click) {
            flag_click = 0;
            state = PET_STATE_JUMPING;
        }
        else if (flag_dclick) {
            flag_dclick = 0;
            state = PET_STATE_WAVING;
        }
        else if (state == working_state && time_reached(next_state_update)) {
            next_state_update = make_timeout_time_ms(100);
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
            next_frame_update = get_absolute_time();
        }

        if (!time_reached(next_frame_update)) {
            sleep_ms(1);
            continue;
        }
        next_frame_update = make_timeout_time_ms(pet_frame_intervals_ms[state]);

        AMOLED_1IN8_DisplayPackedWindow(
            (AMOLED_1IN8.WIDTH - PET_IMAGE_WIDTH) / 2 + pet_image_offset_x,
            (AMOLED_1IN8.HEIGHT - PET_IMAGE_HEIGHT) / 2 + pet_image_offset_y,
            PET_IMAGE_WIDTH,
            PET_IMAGE_HEIGHT,
            PIC[frame].data);
        frame++;
        if (frame >= frame_count) {
            state = (audio_playback_is_busy() || tts_was_busy) ? PET_STATE_WAVING : working_state;
            frame = 0;
            frame_count = pet_state_frame_counts[state];
        }
    }

     /* Module Exit */
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
