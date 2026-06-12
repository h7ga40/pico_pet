#ifndef PETAPP_WAKEWORD_H
#define PETAPP_WAKEWORD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void wakeword_init(void);
bool wakeword_process_frame(const int16_t *pcm, size_t sample_count);
void wakeword_set_debug_enabled(bool enabled);

#endif
