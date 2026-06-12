#ifndef PETAPP_KWS_MODEL_H
#define PETAPP_KWS_MODEL_H

#include <stdbool.h>
#include <stdint.h>

#define KWS_MODEL_WINDOW_SAMPLES 320
#define KWS_MODEL_WINDOW_COUNT 100

typedef struct {
    float negative;
    float near_miss;
    float positive;
} kws_model_scores_t;

void kws_model_init(void);
bool kws_model_add_audio(const int16_t *samples, kws_model_scores_t *scores);

#endif
