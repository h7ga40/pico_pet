#include "wakeword.h"

#include <stdio.h>

#include "kws_model.h"

static bool debug_enabled = true;

void wakeword_init(void)
{
    kws_model_init();
    printf("Wakeword model: window=2s classes=negative,near_miss,positive\n");
}

bool wakeword_process_frame(const int16_t *pcm, size_t sample_count)
{
    if (pcm == NULL || sample_count != KWS_MODEL_WINDOW_SAMPLES) {
        return false;
    }

    kws_model_scores_t scores;
    if (!kws_model_add_audio(pcm, &scores))
        return false;

    if (debug_enabled) {
        printf("Wakeword model: negative=%.3f near_miss=%.3f positive=%.3f\n",
               (double)scores.negative,
               (double)scores.near_miss,
               (double)scores.positive);
    }
    return scores.positive > scores.negative &&
           scores.positive > scores.near_miss;
}

void wakeword_set_debug_enabled(bool enabled)
{
    debug_enabled = enabled;
}
