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
    pio_sm_claim(pico_audio.pio_1, pico_audio.sm_mclk);
    uint offset = pio_add_program(pico_audio.pio_1, &mclk_pio_program);
    mclk_pio_program_init(pico_audio.pio_1, pico_audio.sm_mclk, offset, pico_audio.audio_mclk);
    set_mclk_frequency(pico_audio.mclk_freq);
    pio_sm_set_enabled(pico_audio.pio_1, pico_audio.sm_mclk , true);
}

#define AUDIO_BLOCK_FRAMES       (PICO_SAMPLE_FREQ / 50)
#define INPUT_BUFFER_BLOCKS      50
#define LOOPBACK_DELAY_BLOCKS    25
#define OUTPUT_BUFFER_BLOCKS     2

static int32_t input_buffer[INPUT_BUFFER_BLOCKS][AUDIO_BLOCK_FRAMES];
static int32_t output_buffer[OUTPUT_BUFFER_BLOCKS][AUDIO_BLOCK_FRAMES];
static int loopback_rx_dma = -1;
static int loopback_tx_dma = -1;
static uint32_t input_dma_block;
static volatile uint32_t input_completed_blocks;
static volatile uint32_t output_active_block;
static volatile bool output_ready[OUTPUT_BUFFER_BLOCKS];
static uint32_t last_processed_input_block = UINT32_MAX;
static bool loopback_running;

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
        uint32_t next_block = output_active_block ^ 1u;
        if (output_ready[next_block])
        {
            output_ready[next_block] = false;
            output_active_block = next_block;
        }

        dma_channel_set_read_addr(loopback_tx_dma,
                                  output_buffer[output_active_block], false);
        dma_channel_set_trans_count(loopback_tx_dma, AUDIO_BLOCK_FRAMES, true);
    }
}

void audio_loopback_process(void)
{
    if (!loopback_running)
        return;

    uint32_t completed_blocks = input_completed_blocks;
    if (completed_blocks < LOOPBACK_DELAY_BLOCKS)
        return;

    uint32_t source_sequence = completed_blocks - LOOPBACK_DELAY_BLOCKS;
    if (source_sequence == last_processed_input_block)
        return;

    uint32_t destination_block = output_active_block ^ 1u;
    if (output_ready[destination_block])
        return;

    uint32_t source_block = source_sequence % INPUT_BUFFER_BLOCKS;
    memcpy(output_buffer[destination_block], input_buffer[source_block],
           sizeof(output_buffer[destination_block]));
    output_ready[destination_block] = true;
    last_processed_input_block = source_sequence;
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
    output_ready[0] = false;
    output_ready[1] = false;
    last_processed_input_block = UINT32_MAX;

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

/******************************************************************************
function: Recording and playback loopback test
******************************************************************************/	
void Loopback_test()
{
    audio_loopback_start();
}
