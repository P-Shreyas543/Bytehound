# Bytehound HIL firmware for NUCLEO-G474RE.
#
#   make            build build/bh_sim.elf / .bin / .hex
#   make flash      program over SWD with STM32CubeProgrammer CLI and reset
#   make size       show flash / RAM use
#   make clean
#
# Toolchain: the GNU tools bundled with STM32CubeIDE. Override TOOLCHAIN /
# PROGRAMMER if yours live elsewhere (or put arm-none-eabi-gcc on PATH and
# set TOOLCHAIN=).

CUBEIDE_PLUGINS ?= C:/ST/STM32CubeIDE_2.2.0/STM32CubeIDE/plugins
TOOLCHAIN  ?= $(firstword $(wildcard $(CUBEIDE_PLUGINS)/com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.*/tools/bin))/
PROGRAMMER ?= $(firstword $(wildcard $(CUBEIDE_PLUGINS)/com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.*/tools/bin))/STM32_Programmer_CLI.exe

CC      := $(TOOLCHAIN)arm-none-eabi-gcc
OBJCOPY := $(TOOLCHAIN)arm-none-eabi-objcopy
SIZE    := $(TOOLCHAIN)arm-none-eabi-size

TARGET := build/bh_sim
SRCS   := src/main.c src/startup.c
OBJS   := $(SRCS:src/%.c=build/%.o)

CPU     := -mcpu=cortex-m4 -mthumb -mfloat-abi=soft
CFLAGS  := $(CPU) -std=c11 -O2 -g3 -Wall -Wextra -Werror -Wno-override-init \
           -ffunction-sections -fdata-sections -fno-common
LDFLAGS := $(CPU) -T stm32g474re.ld -Wl,--gc-sections -Wl,-Map=$(TARGET).map \
           --specs=nano.specs --specs=nosys.specs -nostartfiles

all: $(TARGET).elf $(TARGET).bin $(TARGET).hex size

build:
	mkdir -p build

build/%.o: src/%.c src/regs.h | build
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET).elf: $(OBJS) stm32g474re.ld
	$(CC) $(OBJS) $(LDFLAGS) -o $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

size: $(TARGET).elf
	$(SIZE) $<

flash: $(TARGET).elf
	"$(PROGRAMMER)" -c port=SWD mode=UR -w $(TARGET).elf -v -rst

clean:
	rm -rf build

.PHONY: all size flash clean
