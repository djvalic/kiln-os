# Build against a linux-5.10.186 tree prepared by setup.sh:
#   make KDIR=/path/linux-5.10.186          chainload.ko (S00ad5x-kernel)
#   make KDIR=/path/linux-5.10.186 uboot    build-uboot/chainload_uboot.ko:
#     the same source with U-Boot proper's load address 0x80100000, for the
#     bench test tools/bench/ad5x-uboot-chainload only (README.md)
KDIR ?= $(HOME)/workspace/chainload-build/linux-5.10.186
CROSS_COMPILE ?= mipsel-linux-

obj-m := chainload.o
chainload-y := chainload_main.o tramp.o

UBOOT_DIR := $(CURDIR)/build-uboot
UBOOT_FLAGS := -DCHAINLOAD_UBOOT -DCHAINLOAD_LOAD=0x80100000

all:
	cp -f $(CURDIR)/chainload.c $(CURDIR)/chainload_main.c
	$(MAKE) -C $(KDIR) ARCH=mips CROSS_COMPILE=$(CROSS_COMPILE) M=$(CURDIR) modules

# Its own directory and object names: nothing is shared with chainload.ko
uboot:
	mkdir -p $(UBOOT_DIR)
	cp -f $(CURDIR)/chainload.c $(UBOOT_DIR)/chainload_main.c
	cp -f $(CURDIR)/tramp.S $(UBOOT_DIR)/tramp.S
	printf '%s\n' 'obj-m := chainload_uboot.o' \
		'chainload_uboot-y := chainload_main.o tramp.o' \
		'ccflags-y := $(UBOOT_FLAGS)' 'asflags-y := $(UBOOT_FLAGS)' \
		> $(UBOOT_DIR)/Kbuild
	$(MAKE) -C $(KDIR) ARCH=mips CROSS_COMPILE=$(CROSS_COMPILE) M=$(UBOOT_DIR) modules

clean:
	$(MAKE) -C $(KDIR) ARCH=mips CROSS_COMPILE=$(CROSS_COMPILE) M=$(CURDIR) clean
	rm -f chainload_main.c
	rm -rf $(UBOOT_DIR)
