/*****************************************************************************
* | File      	:   audio_pio.c
* | Author      :   Waveshare Team
* | Function    :   ES8311 control related PIO interface
* | Info        :
*----------------
* |	This version:   V1.0
* | Date        :   2025-02-26
* | Info        :   
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
******************************************************************************/

#include <stdlib.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "audio_pio.h"
#include "audio_pio.pio.h"

static bool mclk_initialized;

/******************************************************************************
function: Mclk frequency modification
parameter:
    mclk_freq :  mclk freq
******************************************************************************/								
void set_mclk_frequency(uint32_t mclk_freq) 
{
	double system_clock_frequency = clock_get_hz(clk_sys);
    double div = (system_clock_frequency / mclk_freq) / 5; 
    pio_sm_set_clkdiv(pico_audio.pio_1, pico_audio.sm_mclk, div);
}

/******************************************************************************
function: 16 bit unsigned audio data processing
parameter:
    audio :  16-bit audio array
    len   :  The length of the array 
return:  The address of a 32-bit array
******************************************************************************/	
int32_t* data_treating(const int16_t *audio , uint32_t len)
{
	int32_t *samples = (int32_t *)calloc(len, sizeof(int32_t));
	for(uint32_t i = 0; i < len; i++)
	{
		if(pico_audio.channel_count == 1)
		{
			samples[i] = audio[i] * 65536;
		}
		else
		{
			samples[i] = audio[i] * 65536 + audio[i];
		}
	}
	return samples;
}

/******************************************************************************
function: audio out
parameter:
    samples :  32-bit audio array
    len     :  The length of the array
******************************************************************************/	
void audio_out(int32_t *samples, int32_t len) 
{
	for(uint16_t i = 0; i < len; i++)
	   	pio_sm_put_blocking(pico_audio.pio_2, pico_audio.sm_dout, samples[i]);
}

/******************************************************************************
function: PIO output initialization
parameter:
******************************************************************************/	
void dout_pio_init()
{
    pio_sm_claim(pico_audio.pio_2, pico_audio.sm_dout);
    uint offset = pio_add_program(pico_audio.pio_2, &audio_pio_program);
	audio_pio_program_init(pico_audio.pio_2, pico_audio.sm_dout , offset, pico_audio.audio_dout, pico_audio.audio_lrclk);
	pio_sm_set_clkdiv(pico_audio.pio_2, pico_audio.sm_dout, 1.0f);
    pio_sm_set_enabled(pico_audio.pio_2, pico_audio.sm_dout , true);
}

/******************************************************************************
function: PIO input initialization
parameter:
******************************************************************************/	
void din_pio_init()
{
    pio_sm_claim(pico_audio.pio_1, pico_audio.sm_din);
    uint offset = pio_add_program(pico_audio.pio_1, &read_pio_program);
	read_pio_program_init(pico_audio.pio_1, pico_audio.sm_din , offset, pico_audio.audio_din, pico_audio.audio_lrclk);
    pio_sm_set_clkdiv(pico_audio.pio_1, pico_audio.sm_din, 1.0f);
    pio_sm_set_enabled(pico_audio.pio_1, pico_audio.sm_din , true);
}

/******************************************************************************
function: MCLK pin PIO initialization
parameter:
******************************************************************************/	
void mclk_pio_init()
{
    if (mclk_initialized) {
        set_mclk_frequency(pico_audio.mclk_freq);
        return;
    }

    pio_sm_claim(pico_audio.pio_1, pico_audio.sm_mclk);
    uint offset = pio_add_program(pico_audio.pio_1, &mclk_pio_program);
    mclk_pio_program_init(pico_audio.pio_1, pico_audio.sm_mclk, offset, pico_audio.audio_mclk);
    set_mclk_frequency(pico_audio.mclk_freq);
    pio_sm_set_enabled(pico_audio.pio_1, pico_audio.sm_mclk , true);
    mclk_initialized = true;
}

#define AUDIO_BLOCK_FRAMES       (PICO_SAMPLE_FREQ / 50)
// Keep enough input history to cover one AMOLED refresh without reserving 1 s of SRAM.
#define INPUT_BUFFER_BLOCKS      8
#define OUTPUT_BUFFER_BLOCKS     2
#define PLAY_STREAM_BLOCKS       16

typedef enum {
    PLAYBACK_NONE,
    PLAYBACK_STATIC,
    PLAYBACK_STREAM,
} playback_source_t;

static int32_t input_buffer[INPUT_BUFFER_BLOCKS][AUDIO_BLOCK_FRAMES];
static int32_t output_buffer[OUTPUT_BUFFER_BLOCKS][AUDIO_BLOCK_FRAMES];
static int loopback_rx_dma = -1;
static int loopback_tx_dma = -1;
static uint32_t input_dma_block;
static volatile uint32_t input_completed_blocks;
static volatile uint32_t output_active_block;
static uint32_t last_read_input_sequence = UINT32_MAX;
static bool loopback_running;
static const int16_t *playback_samples;
static size_t playback_sample_count;
static size_t playback_sample_index;
static volatile bool playback_running;
static bool playback_final_block[OUTPUT_BUFFER_BLOCKS];
static playback_source_t playback_source;
static int16_t play_stream[PLAY_STREAM_BLOCKS][AUDIO_BLOCK_FRAMES];
static uint16_t play_stream_counts[PLAY_STREAM_BLOCKS];
static volatile uint32_t play_stream_read_block;
static volatile uint32_t play_stream_write_block;
static volatile uint32_t play_stream_ready_blocks;
static size_t play_stream_expected_samples;
static size_t play_stream_received_samples;

static void playback_fill_block(uint32_t block)
{
    size_t count = 0;
    const int16_t *samples = NULL;

    if (playback_source == PLAYBACK_STATIC) {
        size_t remaining = playback_sample_count - playback_sample_index;
        count = remaining < AUDIO_BLOCK_FRAMES ? remaining : AUDIO_BLOCK_FRAMES;
        samples = &playback_samples[playback_sample_index];
        playback_sample_index += count;
    } else if (playback_source == PLAYBACK_STREAM && play_stream_ready_blocks > 0) {
        uint32_t source_block = play_stream_read_block;
        count = play_stream_counts[source_block];
        samples = play_stream[source_block];
        play_stream_read_block = (source_block + 1) % PLAY_STREAM_BLOCKS;
        play_stream_ready_blocks--;
    }

    for (size_t i = 0; i < count; ++i) {
        int16_t sample = samples[i];
        uint32_t packed = (uint32_t)(uint16_t)sample << 16;
        if (pico_audio.channel_count != 1)
            packed |= (uint16_t)sample;
        output_buffer[block][i] = (int32_t)packed;
    }
    if (count < AUDIO_BLOCK_FRAMES) {
        memset(&output_buffer[block][count], 0,
               (AUDIO_BLOCK_FRAMES - count) * sizeof(output_buffer[block][0]));
    }
    playback_final_block[block] =
        playback_source == PLAYBACK_STATIC && playback_sample_index >= playback_sample_count;
    if (playback_source == PLAYBACK_STREAM && count > 0)
        playback_final_block[block] =
            play_stream_received_samples == play_stream_expected_samples &&
            play_stream_ready_blocks == 0;
}

static void playback_start_locked(void)
{
    dma_channel_abort(loopback_tx_dma);
    dma_channel_acknowledge_irq1(loopback_tx_dma);
    pio_sm_clear_fifos(pico_audio.pio_2, pico_audio.sm_dout);
    playback_running = true;
    output_active_block = 0;
    playback_fill_block(0);
    playback_fill_block(1);
    dma_channel_set_read_addr(loopback_tx_dma, output_buffer[0], false);
    dma_channel_set_trans_count(loopback_tx_dma, AUDIO_BLOCK_FRAMES, true);
}

static void loopback_dma_handler(void)
{
    if (dma_channel_get_irq1_status(loopback_rx_dma))
    {
        dma_channel_acknowledge_irq1(loopback_rx_dma);
        input_completed_blocks++;
        input_dma_block++;
        if (input_dma_block == INPUT_BUFFER_BLOCKS)
            input_dma_block = 0;

        dma_channel_set_write_addr(loopback_rx_dma, input_buffer[input_dma_block], false);
        dma_channel_set_trans_count(loopback_rx_dma, AUDIO_BLOCK_FRAMES, true);
    }

    if (dma_channel_get_irq1_status(loopback_tx_dma))
    {
        dma_channel_acknowledge_irq1(loopback_tx_dma);
        if (playback_running) {
            uint32_t completed_block = output_active_block;
            if (playback_final_block[completed_block]) {
                playback_running = false;
                playback_samples = NULL;
                playback_source = PLAYBACK_NONE;
                memset(output_buffer, 0, sizeof(output_buffer));
                output_active_block = 0;
            } else {
                output_active_block ^= 1u;
                dma_channel_set_read_addr(loopback_tx_dma,
                                          output_buffer[output_active_block], false);
                dma_channel_set_trans_count(loopback_tx_dma, AUDIO_BLOCK_FRAMES, true);
                if (!playback_final_block[output_active_block])
                    playback_fill_block(completed_block);
                return;
            }
        }

        dma_channel_set_read_addr(loopback_tx_dma,
                                  output_buffer[output_active_block], false);
        dma_channel_set_trans_count(loopback_tx_dma, AUDIO_BLOCK_FRAMES, true);
    }
}

static size_t audio_input_copy_block(int16_t *samples, size_t capacity, bool read_next)
{
    if (!loopback_running || samples == NULL || capacity == 0)
        return 0;

    uint32_t completed_blocks = input_completed_blocks;
    if (completed_blocks == 0)
        return 0;

    uint32_t source_sequence = completed_blocks - 1;
    if (read_next) {
        if (last_read_input_sequence == UINT32_MAX)
            last_read_input_sequence = source_sequence;
        else if (last_read_input_sequence >= completed_blocks)
            return 0;
        else if (completed_blocks - last_read_input_sequence > INPUT_BUFFER_BLOCKS)
            last_read_input_sequence = completed_blocks - INPUT_BUFFER_BLOCKS;
        source_sequence = last_read_input_sequence++;
    }

    uint32_t source_block = source_sequence % INPUT_BUFFER_BLOCKS;
    size_t sample_count = capacity < AUDIO_BLOCK_FRAMES ? capacity : AUDIO_BLOCK_FRAMES;
    for (size_t i = 0; i < sample_count; ++i)
        samples[i] = (int16_t)(input_buffer[source_block][i] >> 16);

    return sample_count;
}

size_t audio_input_read_next(int16_t *samples, size_t capacity)
{
    return audio_input_copy_block(samples, capacity, true);
}

size_t audio_input_read_latest(int16_t *samples, size_t capacity)
{
    return audio_input_copy_block(samples, capacity, false);
}

size_t audio_input_copy_latest(int16_t *samples, size_t capacity)
{
    return audio_input_copy_block(samples, capacity, false);
}

bool audio_play_pcm16_start(const int16_t *samples, size_t sample_count)
{
    if (!loopback_running || playback_source != PLAYBACK_NONE ||
        samples == NULL || sample_count == 0)
        return false;

    irq_set_enabled(DMA_IRQ_1, false);
    playback_samples = samples;
    playback_sample_count = sample_count;
    playback_sample_index = 0;
    playback_source = PLAYBACK_STATIC;
    playback_start_locked();
    irq_set_enabled(DMA_IRQ_1, true);
    return true;
}

bool audio_play_stream_start(size_t sample_count)
{
    if (!loopback_running || playback_source != PLAYBACK_NONE || sample_count == 0)
        return false;

    irq_set_enabled(DMA_IRQ_1, false);
    playback_source = PLAYBACK_STREAM;
    playback_running = false;
    play_stream_read_block = 0;
    play_stream_write_block = 0;
    play_stream_ready_blocks = 0;
    play_stream_expected_samples = sample_count;
    play_stream_received_samples = 0;
    irq_set_enabled(DMA_IRQ_1, true);
    return true;
}

size_t audio_play_stream_writable_samples(void)
{
    if (playback_source != PLAYBACK_STREAM ||
        play_stream_ready_blocks >= PLAY_STREAM_BLOCKS ||
        play_stream_received_samples >= play_stream_expected_samples)
        return 0;

    size_t remaining = play_stream_expected_samples - play_stream_received_samples;
    return remaining < AUDIO_BLOCK_FRAMES ? remaining : AUDIO_BLOCK_FRAMES;
}

bool audio_play_stream_write(const int16_t *samples, size_t sample_count)
{
    size_t writable = audio_play_stream_writable_samples();
    if (samples == NULL || sample_count == 0 || sample_count != writable)
        return false;

    irq_set_enabled(DMA_IRQ_1, false);
    uint32_t block = play_stream_write_block;
    memcpy(play_stream[block], samples, sample_count * sizeof(samples[0]));
    play_stream_counts[block] = (uint16_t)sample_count;
    play_stream_write_block = (block + 1) % PLAY_STREAM_BLOCKS;
    play_stream_ready_blocks++;
    play_stream_received_samples += sample_count;
    if (!playback_running)
        playback_start_locked();
    irq_set_enabled(DMA_IRQ_1, true);
    return true;
}

bool audio_playback_is_busy(void)
{
    return playback_source != PLAYBACK_NONE;
}

void audio_loopback_start(void)
{
    if (loopback_running)
        return;

    memset(input_buffer, 0, sizeof(input_buffer));
    memset(output_buffer, 0, sizeof(output_buffer));

    mclk_pio_init();
    din_pio_init();
    dout_pio_init();

    loopback_rx_dma = dma_claim_unused_channel(true);
    loopback_tx_dma = dma_claim_unused_channel(true);
    input_dma_block = 0;
    input_completed_blocks = 0;
    output_active_block = 0;
    playback_running = false;
    playback_source = PLAYBACK_NONE;
    playback_final_block[0] = false;
    playback_final_block[1] = false;
    last_read_input_sequence = UINT32_MAX;

    dma_channel_config rx_config = dma_channel_get_default_config(loopback_rx_dma);
    channel_config_set_transfer_data_size(&rx_config, DMA_SIZE_32);
    channel_config_set_read_increment(&rx_config, false);
    channel_config_set_write_increment(&rx_config, true);
    channel_config_set_dreq(&rx_config,
                            pio_get_dreq(pico_audio.pio_1, pico_audio.sm_din, false));
    dma_channel_configure(loopback_rx_dma, &rx_config,
                          input_buffer[input_dma_block],
                          &pico_audio.pio_1->rxf[pico_audio.sm_din],
                          AUDIO_BLOCK_FRAMES, false);

    dma_channel_config tx_config = dma_channel_get_default_config(loopback_tx_dma);
    channel_config_set_transfer_data_size(&tx_config, DMA_SIZE_32);
    channel_config_set_read_increment(&tx_config, true);
    channel_config_set_write_increment(&tx_config, false);
    channel_config_set_dreq(&tx_config,
                            pio_get_dreq(pico_audio.pio_2, pico_audio.sm_dout, true));
    dma_channel_configure(loopback_tx_dma, &tx_config,
                          &pico_audio.pio_2->txf[pico_audio.sm_dout],
                          output_buffer[output_active_block],
                          AUDIO_BLOCK_FRAMES, false);

    irq_set_exclusive_handler(DMA_IRQ_1, loopback_dma_handler);
    dma_channel_set_irq1_enabled(loopback_rx_dma, true);
    dma_channel_set_irq1_enabled(loopback_tx_dma, true);
    irq_set_enabled(DMA_IRQ_1, true);

    loopback_running = true;
    dma_start_channel_mask((1u << loopback_rx_dma) | (1u << loopback_tx_dma));
}
