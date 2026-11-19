# Kiln OS documentation

Every page, grouped by what you want to do. New to the code? Start with
[architecture.md](architecture.md), then the [glossary](glossary.md) and
[CONTRIBUTING.md](../CONTRIBUTING.md).

Pages marked *(private for now)* are in the development repository but
not yet in the public copy on GitHub.

## Using Kiln OS

- [install.md](install.md): installing from stock (USB stick or SSH), and going back to stock.
- [updates.md](updates.md): how releases are made and how the printer installs them.
- [sponsoring.md](sponsoring.md): sponsoring Kiln OS, and what it does and doesn't mean.
- [recovery-os.md](recovery-os.md): the recovery system in slot A: updates, backup, restore, USB rescue.
- [ab-updates.md](ab-updates.md): A/B updates (prototype for 2.0, opt-in): the main OS in both slots, SWUpdate and U-Boot's boot count.
- [own-boot-loader.md](own-boot-loader.md): Kiln's own boot loader (experimental, opt-in): known boards, the risk, installing it from the recovery OS, building it yourself, going back.
- [deviations-from-stock.md](deviations-from-stock.md): every behaviour that differs from stock, what to watch for, how to go back.
- [config-layout.md](config-layout.md): which Klipper config file holds what, and which ones you edit.
- [print-start.md](print-start.md): what happens at the start of a print (mesh, prime line, heat soak).
- [setup-wizard.md](setup-wizard.md): the first-boot setup wizard on the touch screen (design and contract).
- [plugins.md](plugins.md): switching plugins on and off, installing them.
- [zmod-compat.md](zmod-compat.md): printing G-code made for zMod and Bambufy.
- [orcaslicer.md](orcaslicer.md): OrcaSlicer with Kiln OS.
- [sound.md](sound.md): the speaker, chimes, `M300` and MIDI files.
- [logs.md](logs.md): where the logs are and how to get more detail.
- [memory.md](memory.md): 256 MiB and 512 MiB boards, and what Kiln OS changes at start-up for each.
- [ifs-troubleshooting.md](ifs-troubleshooting.md): when the IFS drops off.

## Writing plugins

- [plugins.md](plugins.md): what a plugin is, where it lives, how it is loaded.
- [plugin-api.md](plugin-api.md): the interface a plugin may rely on, by API version.
- [stability.md](stability.md): what stays the same in every 1.x release, and what can change.
- [plugin-root-hooks.md](plugin-root-hooks.md): root scripts a plugin can bring (`root/install.sh`, `update.sh`, `uninstall.sh`, boot scripts), as zMod has them.
- [api.md](api.md): everything Kiln OS adds to Klipper and Moonraker, for slicer plugins, dashboards and other clients.
- [data-layout.md](data-layout.md): the files and switches on the data partition.

## Working on the code

- [../CONTRIBUTING.md](../CONTRIBUTING.md): building, tests, the rules for a change, how pull requests are taken.
- [architecture.md](architecture.md): how the pieces fit, where each lives in the repo, how a change reaches a printer.
- [glossary.md](glossary.md): the words used in the code and docs.
- [boot-order.md](boot-order.md): every start-up script of both systems, in order, with the files each reads and writes.
- [data-layout.md](data-layout.md): `/data/ad5x` and `/run`: writer, reader and meaning of each file.
- [../buildroot/README.md](../buildroot/README.md): the Buildroot tree, the images and what they contain.
- [boot-slots.md](boot-slots.md): the boot loader, the A/B slots and the boot flag (ends with an install log of the first unit).
- [helixscreen-integration.md](helixscreen-integration.md): what the touch screen needs from Klipper and Moonraker, and how Kiln OS provides it.
- [releasing.md](releasing.md): cutting a release with `tools/release.sh`. *(private for now)*
- [roadmap.md](roadmap.md): future work, not scheduled. *(private for now)*
- [brand/README.md](brand/README.md): logo, colours and rules for new screens. *(private for now)*
- `kernel-ingenic66/README.md`, `kernel-ingenic66/chainload/README.md`: Kiln's 6.6 kernel and the chainload module.
- `kernel-mainline/README.md`: the opt-in mainline 7.3 kernel.
- `klipper/mcu-dicts/README.md`: the board firmware versions an image carries.
- `klipper/plugins/*/README.md`: the shipped plugins.
- `translations/ru/README.md`: the Russian translation kit.

## Hardware and stock behaviour

- [mcu-flashing.md](mcu-flashing.md): how the boards are flashed, by stock and by Kiln OS, and the way back.
- [motion-mcu.md](motion-mcu.md): the stock board firmware (control 1.1.1) and what it is built from. *(private for now)*
- [ifs-protocol.md](ifs-protocol.md): the IFS serial protocol, as far as it is known.
- [bed-weighing-board.md](bed-weighing-board.md): the load-cell board and stock's Z routine.
- [klipper-fork-diff.md](klipper-fork-diff.md): what Flashforge changed in its Klipper fork and what replaces it.
- [boot-slots.md](boot-slots.md): the SPL and the eMMC layout (also listed above).
- [emmc-repair.md](emmc-repair.md): checking, backing up and repairing the eMMC from a Linux PC over USB (J28), when nothing on it starts.
- [serial-console.md](serial-console.md): the mainboard's DEBUG header (UART0, 3.3 V): our kernel's console and a root login without a network, and why everything before our kernel is silent there.

## Internal notes

Lab notes from bring-up and research. They record how things were found
out, may be out of date, and are not guides. Most are private for now.

- [bring-up.md](bring-up.md): hardware bring-up log of mainline Klipper on the first unit. *(private for now)*
- [emmc-backup.md](emmc-backup.md): how the first unit's eMMC was backed up.
- [builder.md](builder.md): the maintainer's update builder. *(private for now)*
- [update-signing.md](update-signing.md): using the signing key on the build server (signing is off by default). *(private for now)*
- [mips-test-plan.md](mips-test-plan.md): MIPS and kernel test plan (X2600 / XBurst2). *(private for now)*
- [mips-test-plan-boot.md](mips-test-plan-boot.md): kernel test boot of held-back eMMC and CMA changes. *(private for now)*
- [qemu-stock.md](qemu-stock.md): running stock AD5X programs on a PC under qemu-user. *(private for now)*
- [stock-firmware-3.1.0.md](stock-firmware-3.1.0.md): unpack notes of the stock 3.1.0 firmware. *(private for now)*
- [ifs-swap-capture.md](ifs-swap-capture.md): stock IFS behaviour, recorded from the stock app. *(private for now)*
- [ifs-swap-sequence.md](ifs-swap-sequence.md): stock colour-swap sequence (draft). *(private for now)*
- [camera-plugin-security.md](camera-plugin-security.md): security requirements for camera control. *(private for now)*
