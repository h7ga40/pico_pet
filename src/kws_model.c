#include "kws_model.h"

#include <math.h>
#include <stddef.h>

#include "kws_model_weights.h"

static float features[KWS_MODEL_WINDOW_COUNT * 2];
static size_t feature_window;

static void dense_relu(const float *input, size_t input_size,
                       const float *weights, const float *bias,
                       float *output, size_t output_size)
{
    for (size_t row = 0; row < output_size; ++row) {
        float value = bias[row];
        for (size_t column = 0; column < input_size; ++column)
            value += weights[row * input_size + column] * input[column];
        output[row] = value > 0.0f ? value : 0.0f;
    }
}

static void infer(kws_model_scores_t *scores)
{
    float hidden1[24];
    float hidden2[12];
    float logits[3];

    dense_relu(features, 200, &g_kws_dense1_weights[0][0],
               g_kws_dense1_bias, hidden1, 24);
    dense_relu(hidden1, 24, &g_kws_dense2_weights[0][0],
               g_kws_dense2_bias, hidden2, 12);

    float maximum = -INFINITY;
    for (size_t row = 0; row < 3; ++row) {
        float value = g_kws_scores_bias[row];
        for (size_t column = 0; column < 12; ++column)
            value += g_kws_scores_weights[row][column] * hidden2[column];
        logits[row] = value;
        if (value > maximum)
            maximum = value;
    }

    float probabilities[3];
    float total = 0.0f;
    for (size_t i = 0; i < 3; ++i) {
        probabilities[i] = expf(logits[i] - maximum);
        total += probabilities[i];
    }
    scores->negative = probabilities[0] / total;
    scores->near_miss = probabilities[1] / total;
    scores->positive = probabilities[2] / total;
}

void kws_model_init(void)
{
    feature_window = 0;
}

bool kws_model_add_audio(const int16_t *samples, kws_model_scores_t *scores)
{
    double sum_squares = 0.0;
    int32_t peak = 0;
    for (size_t i = 0; i < KWS_MODEL_WINDOW_SAMPLES; ++i) {
        int32_t sample = samples[i];
        int32_t magnitude = sample < 0 ? -sample : sample;
        if (magnitude > peak)
            peak = magnitude;
        float normalized = (float)sample / 32768.0f;
        sum_squares += (double)normalized * normalized;
    }

    features[feature_window * 2] = sqrtf((float)(sum_squares / KWS_MODEL_WINDOW_SAMPLES));
    features[feature_window * 2 + 1] = (float)peak / 32768.0f;
    if (++feature_window < KWS_MODEL_WINDOW_COUNT)
        return false;

    infer(scores);
    feature_window = 0;
    return true;
}
