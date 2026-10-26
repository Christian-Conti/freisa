<!--
  Copyright 2026 FREISA contributors
  Apache License, Version 2.0, see LICENSE.md for details.
  SPDX-License-Identifier: Apache-2.0

  Info     : The bundled examples: what they do, how to build, program and test them on every board.
  Module   : 7-examples.md
  Author   : Christian Conti
  Contact  : christian.conti@mail.it
-->
# 7. Examples

Two examples come with FREISA. Each one is a project file in `designs/examples/` plus its RTL and pin files in
`examples/<name>/`.

| Example | What it does | pynq-z2 (PYNQ-Z1/Z2) | ZCU104 | ZCU106 | KV260 | AUP-ZU3 8 GB |
|---------|--------------|----------------------|--------|--------|-------|--------------|
| `blinky` | LED 0 blinks | `.bit`, open tools | `.bit` (`open_io`) | `.bit` (`open_io`) | routed checkpoint only | `.bit` (`open_io`) |
| `uart_loopback` | echoes the PL UART | — | `.bit` + `python freisa.py uart-test` | `.bit` + `python freisa.py uart-test` | — | — |

`open_io` ([details](8-open-io.md)): every step is done by open tools, I/O included; Vivado only runs `write_bitstream` (no open bitstream writer
exists for UltraScale+). A dash means the board cannot run the example (see the notes of each example).

## blinky
A 26-bit counter whose top bit drives an LED.

| File | Content |
|------|---------|
| `designs/examples/blinky.yml` | project file, every entry explained in [Project files](3-projects.md#the-blinky-project-entry-by-entry) |
| `examples/blinky/blinky.v` | the design (`clk`, `led`) |
| `examples/blinky/blinky_diff.v` | top with a differential clock, used only by the Vivado alternatives |
| `examples/blinky/<board>.xdc` | clock and LED pins of each board |

```sh
python freisa.py run                      # = -d blinky -t pynq-z2: RTL -> out.bit with open tools
python freisa.py upload                   # program it
python freisa.py run -t zcu104 && python freisa.py upload -t zcu104
python freisa.py run -t aup-zu3-8gb       # AUP-ZU3: 100 MHz LVDS clock, white LED 0
python freisa.py run -t kv260 --to route  # KV260: no PL clock oscillator, stops at the routed checkpoint
```
Result: `build/blinky/<board>/out.bit`; on the board LED 0 blinks (period of 2^26 clock cycles: about 2 Hz on PYNQ at 125 MHz, about 4.5 Hz on ZCU10x at 300 MHz).

## uart_loopback
Whatever the PC sends on the FPGA's UART comes back unchanged, at any baud rate (the receive line is synchronised with
two flip-flops and drives the transmit line). LED 0 flashes on every received byte.
On ZCU104 and ZCU106 the USB cable used for JTAG also carries this UART (another channel of the same FTDI chip), so one
cable programs the board and runs the test.

| File | Content |
|------|---------|
| `designs/examples/uart_loopback.yml` | project file (same keys as blinky) |
| `examples/uart_loopback/uart_loopback.v` | the design (`clk`, `rx`, `tx`, `led`) |
| `examples/uart_loopback/<board>.xdc` | PL UART, clock and LED pins of ZCU104 and ZCU106 |

```sh
python freisa.py run -d uart_loopback -t zcu104
python freisa.py upload -d uart_loopback -t zcu104
python freisa.py uart-test                          # finds the connected board and its serial port, sends 256 random bytes
python freisa.py uart-test -t zcu104 --baud 921600  # or a given board / baud rate; --port /dev/ttyUSBx to force the port
```
Expected: `✔ echo matches: sent 256, received 256`. If nothing comes back, check that uart_loopback (not blinky) is
loaded on the board.

Not available on PYNQ-Z1/Z2, KV260 and AUP-ZU3: their USB serial port is wired only to the processor (PS), not to FPGA pins, so a
design in the FPGA cannot reach it. There a loopback needs software on the processor, or an external USB-serial adapter
on PMOD pins (with its own pin file).

## Using an example as a template
Copy a project file to `designs/<name>.yml`, change `repo`, `top`, `rtl` and the pin files, and run
`python freisa.py run -d <name> -t <board>`. `python freisa.py check -d <name> -t <board>` tells you what is missing.
