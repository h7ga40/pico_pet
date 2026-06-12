#include "wakeword.h"

#include <stdio.h>

#define LOUDNESS_THRESHOLD 3000
#define REQUIRED_LOUD_FRAMES 3
#define DEBUG_PRINT_INTERVAL_FRAMES 25

static uint32_t loud_frame_count;
static uint32_t processed_frame_count;
static bool debug_enabled = true;

void wakeword_init(void)
{
    loud_frame_count = 0;
    processed_frame_count = 0;
    printf("Wakeword stub: threshold=%d required_frames=%d\n",
           LOUDNESS_THRESHOLD,
           REQUIRED_LOUD_FRAMES);
}

bool wakeword_process_frame(const int16_t *pcm, size_t sample_count)
{
    if (pcm == NULL || sample_count == 0) {
        return false;
    }

    int64_t sum_squares = 0;
    int32_t peak = 0;
    for (size_t i = 0; i < sample_count; ++i) {
        const int32_t sample = pcm[i];
        const int32_t magnitude = sample < 0 ? -sample : sample;
        if (magnitude > peak) {
            peak = magnitude;
        }
        sum_squares += (int64_t)sample * sample;
    }

    const int64_t mean_square = sum_squares / (int64_t)sample_count;
    const int64_t threshold_square = (int64_t)LOUDNESS_THRESHOLD * LOUDNESS_THRESHOLD;
    const bool is_loud = mean_square >= threshold_square;

    loud_frame_count = is_loud ? loud_frame_count + 1 : 0;
    ++processed_frame_count;
    if (debug_enabled && ((processed_frame_count % DEBUG_PRINT_INTERVAL_FRAMES) == 0 || is_loud)) {
        printf("Wakeword audio: mean_square=%lld peak=%ld loud_frames=%lu\n",
               mean_square,
               (long)peak,
               (unsigned long)loud_frame_count);
    }

    if (loud_frame_count < REQUIRED_LOUD_FRAMES) {
        return false;
    }

    loud_frame_count = 0;
    return true;
}

void wakeword_set_debug_enabled(bool enabled)
{
    debug_enabled = enabled;
}
