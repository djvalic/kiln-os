# Russian translation: what is missing or untranslated

Kiln OS's touch screen is HelixScreen v1.1.0-rc.1 with Kiln's patches. This list was made on 2026-11-11 and
brought up to date on 2026-11-19 with Kiln's HelixScreen patches up to 0085, and on 2026-11-21 with the patches up
to 0093 and all of the recovery screen's lines. It was made from
[helixscreen-ru.yml](helixscreen-ru.yml) and [helixscreen-en.yml](helixscreen-en.yml) in this folder, and from
the recovery screen's [en.txt](../../recovery-ui/i18n/en.txt) and [ru.txt](../../recovery-ui/i18n/ru.txt).

## Summary

- `helixscreen-en.yml` has 5046 keys. `helixscreen-ru.yml` has the same 5046 keys: none is missing.
- 112 Russian values are the same as the English text. They are names, units and numbers that stay as they are, and `Pressure Advance`, which stays English on purpose (section 4).
- 7 more values have no Cyrillic but differ from English on purpose (for example `AMS` reads `IFS`, `WiFi` reads `Wi-Fi`).
- 371 keys belong to Kiln OS's own screens. I wrote their Russian myself, so they need a native speaker's check most (section 5). 14 of them are new since the last list: Boot into recovery, Log detail, the two Auto-Refill rows of the IFS settings, and SELECTOR and HUB on the IFS drawing. 5 more are new since then: the IFS messages that said AMS in English (section 5); their Russian is the one the AMS messages already had. 54 more are new with patches 0071 to 0077 (section 5): Reboot and Shutdown asking one action at a time, Return to Flashforge firmware, Extended memory, and the IFS firmware switch. 3 more are new with patches 0078 and 0079: the eMMC row of Settings > About, and 7 with patches 0081 and 0082: the Processor row next to it (section 5). 52 more are new with patches 0084 and 0085: the setup wizard's Filament step, what a running step is doing (action, temperatures, time), the Z offset test's slot and temperatures, "Remove the test print from the bed", and naming the slot in the toolhead when Kiln can't tell it (section 5), and one more step name for the logs, `Ad5xFilament`. 2 more are new with patch 0088: the question
"Run the setup wizard?" at the first start after Kiln OS is installed again over Flashforge's firmware (section 5,
Setup wizard). 4 more are new with patch 0094: the one-off notices that a boot loader update is ready, or that
Kiln OS has its own boot loader for this printer (section 5, end). Patches 0086, 0087 and 0089 to 0093 add no text. Patch 0080 changed some Russian wording (section 2).
- 41 keys are new in HelixScreen v1.1.0-rc.1, and the 41 that came with v1.1.0-beta.18 are still unchecked. HelixScreen ships Russian for all of them, so nothing shows in English, but nobody here has checked that Russian yet (section 7). rc.1 also removed 9 older keys whose texts it rewrote (the HelixPrint plugin reasons and the tour).
- A few open questions and texts that are still English on the screen (section 1).
- Recovery screen: all 306 lines of `ru.txt` have a first Russian version that needs checking (section 6). Section 6
  now lists every line; new in this update are the Return to Flashforge firmware page, Kiln's boot loader pages, the
  automatic update at start, the reasons why something is not possible now, and the home screen's last update. New on
  2026-11-22: the boot loader line on Reboot / Power (9 lines, `bl_line_*`), with the line for an older build in the
  recovery OS, and the Return to Flashforge page's note that Flashforge's own boot loader can't be put back
  (`rs_spl_missing`).

## 1. Open items

**HelixScreen's own wizard titles that are probably cut off.** I measured them with the screen font against the place where
"лоток для отхо" was cut in the issue #23 photo; I have not seen them on the screen. A shorter Russian would help:

- `Printer Setup: Filament Sensor` = `Настройка принтера: Датчик филамента` (HelixScreen)
- `Printer Setup: Identity` = `Настройка принтера: Идентификация` (HelixScreen)
- `Printer Setup: Input Shaping` = `Настройка принтера: Компенсация вибраций` (HelixScreen)
- `Printer Setup: Touch Calibration` = `Настройка принтера: Калибровка сенсора` (HelixScreen)

**Still English on the screen.** Nothing to translate in the file; these need a code change:

- Status lines that come from the printer itself (Klipper), not from the screen: for example the progress text of a
  wizard step and the bed heat soak test lines. These are English in every language for now.
- The print start steps on the print status screen (patch 0067) show the printer's own words, for example
  `Heating bed and nozzle`, `Checking Z` or `Prime line`. They come from Kiln's print start, not from this file.

**Recovery screen:** a first Russian version to check (section 6).

## 2. Fixed so far

### One language on the screen (2026-11-21)

- Recovery screen: the reason after `Сейчас невозможно:` was the tool's English text (for example `busy:
  start-up-actions (wait for it to finish)`), and the home screen's `Последнее обновление:` showed the English line of
  the update log. Both are Russian now (section 6: "Why something is not possible now" and "Last update on the home
  screen").
- Touch screen: the question "Run the setup wizard?" (patch 0088) had Russian and English only, so in German and the
  other languages its English text sat above translated buttons. Every language has it now.

### HelixScreen patch 0080 and the recovery screen

- Stock firmware is `стоковая прошивка` everywhere, as in the IFS firmware switch: `Restart into the recovery OS to put Flashforge's own firmware back` = `... вернуть стоковую прошивку Flashforge`, and the recovery screen's `родная` lines (section 6) say `стоковая` (`стоковый загрузчик` for the boot loader).
- The Return to Flashforge firmware dialog names the recovery screen's button as it reads, `Вернуть Flashforge` (in English `Return to Flashforge`). The English key changed with it (section 5).
- Extended memory: a printer restart is `перезагрузка`, as in Reboot and Shutdown: `Restart now?` = `Перезагрузить сейчас?`, `... после перезагрузки.` The notice now also says `по умолчанию она выключена`, as the English does.

### After Kiln OS v0.0.60

- Auto-Refill is `Автозамена` everywhere now, as on the screen. Four texts still said `автопополнение`: `Filament ran out. Auto-Refill is off, ...` (`Автозамена выключена, ...`), `Load a new spool in this slot, or turn on Auto-Refill ...` (`... включите автозамену ...`), `RFID, Auto-Refill, nozzle and link care` (`RFID, автозамена, ...`) and `Toggle Auto-Refill` (`Переключить автозамену`). `Auto-Replenish` and the other `Replenish` texts are a different feature of other units and keep `пополнение`.

### Kiln OS v0.0.58: alexshev86's fixes (PR #49)

- `Connected ...` = `Подключено ...` in all the connection status lines; `12 Hour` / `24 Hour` = `12-часовой` /
  `24-часовой`; ё where it was missing (её, ведёт); «» instead of straight quotes (`«Проверить снова»`, `«{}»`,
  `«Timer Too Close»`); `%d с` instead of `%ds` in the two rotation countdowns.
- Homing is `паркуется` / `паркует все оси` instead of `ищет ноль`, also in `Home and sweep the cutter...`
  (`Запарковать оси и прощупать резак, ...`).
- `BACK`, the rear-edge label of the belt drawing, is `СЗАДИ`.
- `· Tuned in {} round` / `· Tuned in {} rounds` = `· Настроено за {} раунд` / `· Раундов настройки: {}`. The screen
  takes the first for 1 and the second for every other number, and does not read plural forms for these two, so
  the second must fit any number.
- A dash between words is the long dash with spaces (` — `), not a hyphen ` - ` or ` – `. Hyphens that are signs
  stay: `нажмите - или +`, the `+ - _ . ( ) /` list and the `PLA - Чёрный` example.
- Recovery screen: the main menu tiles `install_update` = `Обновление` (`Установить обновление` did not fit) and
  `reboot_power` = `Питание`.

### Kiln OS v0.0.52

- The setup wizard's step descriptions, the summary rows and the two `... Klipper will restart.` messages are in the
  file now, with my Russian (section 5, setup wizard). Please check them.
- The wizard's `Back` and `Cancel` buttons and the two Filament auto-refill dropdowns (`Exact` / `Similar` /
  `Any colour`, `Slot per file` / `Auto colour`) now show their Russian.
- No Russian value uses `→` or `№` any more (section 3).
- Shorter so they fit: `Printer Setup: Purge Box` = `Настройка принтера: лоток` (was cut off as "лоток для отхо"),
  `Printer Setup: Vibration Compensation` = `Настройка принтера: вибрации`, `Printer Setup: Z Offset` = `Настройка принтера: смещение Z`,
  and the button `Save & Restart` = `Сохр. и рестарт` (`Сохранить и перезапустить` was cut off).
- `Changing filament` = `Смена филамента`: the IFS status line when a filament change starts outside the screen
  (for example from a print's own G-code) is translated now.

## 3. Characters the screen cannot draw

The screen font has Latin, Cyrillic and these signs: `° « » — – · … × ² •` and the usual quotes. It has no arrow `→`
and no `№`: both show as an empty box. Instead of `→` use `—` or a colon; instead of `№` use `#` or the word `номер`.
A few keys (left-hand side) still contain `→`, for example `{} → {}: no filament loaded.`: keep the key as it is,
only the Russian on the right must not use it.

## 4. Same as English in helixscreen-ru.yml

Kept in English on purpose: Russian 3D printing texts usually keep `Pressure Advance` (or `PA`), zMod's Russian
documentation does too, and the stock Flashforge screen has no such setting. Say so if you would translate it:

- `Pressure Advance` = `Pressure Advance` (advanced_panel.xml, calibration_pa_panel.xml)
- `Pressure Adv.` = `Pressure Adv.` (controls_panel.xml)
- `Pressure advance` = `Pressure Advance` (pa_tuning_overlay.xml, ui_overlay_pa_tuning.cpp)

Fine as they are:

- Names and abbreviations: `ABS`, `ADXL`, `AFC`, `Allwinner`, `Android logcat`, `BEACON`, `Bluetooth`, `Brother PT (Bluetooth)`, `Brother QL`, `Brother QL (Bluetooth)`, `CARTOGRAPHER`, `CPU`, `"CPU: "`, `Klipper: {}`, `Creality CFS`, `Creality K1`, `Creality K2 Plus`, `Elegoo Centauri Carbon`, `eMMC`, `Ethernet`, `FlashForge Adventurer 5M`, `FlashForge Adventurer 5X`, `FlashForge Creator 5`, `FlashForge Creator 5 Pro`, `FlashForge IFS`, `Flowguard`, `HE`, `HELIXSCREEN`, `HEPA`, `Happy Hare MMU`, `HelixScreen`, `IP:`, `Kalico`, `Klipper`, `"Klipper: "`, `LOT-2024-001`, `MAC:`, `MCU`, `"MCU: "`, `MPC`, `MakeID (Bluetooth)`, `Moonraker`, `"Moonraker: "`, `Niimbot (Bluetooth)`, `OD`, `OK`, `OS`, `PA`, `PETG`, `PID`, `PLA`, `Phomemo (Bluetooth)`, `Phomemo M110`, `Polymaker`, `QGL`, `RAM`, `RH`, `RSS`, `RSS:`, `Raspberry Pi`, `Raspberry Pi (32-bit)`, `Shake&Tune`, `Snapmaker SnapSwap`, `Snapmaker U1`, `Spoolman`, `Sysfs`, `TPU`, `USB`, `WPA/WPA2`, `WPA3`, `Wi-Fi`, `Wi-Fi {}`, `XY`
- Numbers, units and placeholders only: `%d-%d`, `%d-%d°C`, `%d mm/s`, `--°C`, `...`, `0°`, `170-300 °C`, `180°`, `270°`, `50W`, `5V`, `90°`, `A`, `X`, `X:`, `Y`, `Y:`, `Z`, `Z:`, `Z: 0.000`, `{} ({})`, `{} · {}`, `{} · {} · {}`, `{}, {}`
- Internal step names (only in log files, never on the screen): `InputShaper`, `Ad5xFinish`, `Ad5xIfs`, `Ad5xMesh`, `Ad5xNozzle`, `Ad5xPid`, `Ad5xSelfcheck`, `Ad5xShaper`, `Ad5xSoak`, `Ad5xSummary`, `Ad5xTimezone`, `Ad5xTrash`, `Ad5xZoffset`

Different from English on purpose, no Cyrillic:

- `AMS` = `IFS`
- `LEDs` = `LED`
- `MCUs` = `MCU`
- `WiFi` = `Wi-Fi`
- `Wifi` = `Wi-Fi`
- `{} MCUs` = `{} MCU`

## 5. Kiln OS's own screens

367 keys come from Kiln OS, not from HelixScreen. All but twelve are near the end of `helixscreen-ru.yml`: the
blocks that start with a `# ... (patch 00xx)` comment line, from `# Kiln's tour (patch 0058, tour_steps_kiln.cpp)`
on, and the alphabetical list after `~{:.1f} Hz / turn`, starting with `, corners {:+.3f} to {:+.3f}` (in
`helixscreen-en.yml` all of them come after the line `# Kiln OS (AD5X) strings from the Kiln HelixScreen
patches`). The other twelve are the chamber light lines
near the top (`Chamber light off when the screen sleeps` and the one after it) and the ten eMMC and Processor
strings of Settings > About, each at its alphabetical place (section 5 lists them). Keep IFS as IFS: it is the name of
the filament unit. (The 13 `Ad5x...` step names there are only used in log files; leave them.)

<details><summary>Setup wizard (66)</summary>

- `Applying {}... Klipper restarts.`
  = `Применение {}... Klipper перезапускается.`
- `Asks for the time zone and the nozzle size, then runs the self-check and the tuning steps again (PID, bed mesh, vibration, IFS, Z offset). Every step can be skipped. Results are saved at the end and Klipper restarts.`
  = `Запрашивает часовой пояс и размер сопла, затем снова выполняет самопроверку и шаги настройки (PID, сетка стола, вибрации, IFS, смещение по Z). Любой шаг можно пропустить. В конце результаты сохраняются, и Klipper перезапускается.`
- `Away 0.01`
  = `Дальше 0.01`
- `Away 0.05`
  = `Дальше 0.05`
- `Bed heat soak calibration (optional)`
  = `Калибровка прогрева стола (необязательно)`
- `Bed soak`
  = `Прогрев стола`
- `Calibrates the bed heat soak: how long the bed keeps warming after it reaches 60 °C, so the first layer stays flat. Takes about 15 minutes and starts from a cold bed. Skip it if you don't need it.`
  = `Калибрует прогрев стола: сколько стол ещё прогревается после достижения 60 °C, чтобы первый слой оставался ровным. Занимает около 15 минут и начинается с холодного стола. Если это не нужно, пропустите шаг.`
- `Check that every part of the printer answers`
  = `Проверка, что все узлы принтера отвечают`
- `Check the nozzle is over the trash bin`
  = `Проверьте, что сопло над лотком для отходов`
- `Checks the boards, IFS, accelerometer, bed scale, filament sensor and fans, homes, and heats nozzle and bed briefly. Fans and heaters each run for about 10 seconds and switch off again.`
  = `Проверяет платы, IFS, акселерометр, тензодатчик стола, датчик филамента и вентиляторы, паркует оси и ненадолго нагревает сопло и стол. Вентиляторы и нагреватели работают около 10 секунд каждый и снова выключаются.`
- `Closer 0.01`
  = `Ближе 0.01`
- `Closer 0.05`
  = `Ближе 0.05`
- `Estimate first`
  = `По оценке`
- `Factory`
  = `Сброс`
- `FAIL`
  = `СБОЙ`
- `Faster, reliable filament swaps`
  = `Быстрая и надёжная смена филамента`
- `First-layer test print with live adjustment`
  = `Тестовая печать первого слоя с подстройкой на ходу`
- `Heats the bed to 60 °C and probes the whole bed to measure its shape. Keep the bed clear. The bed stays warm for the Z offset test that follows.`
  = `Нагревает стол до 60 °C и проходит датчиком по всему столу, чтобы измерить его форму. Стол должен быть пустым. Стол остаётся тёплым для следующего теста смещения по Z.`
- `IFS tuning`
  = `Настройка IFS`
- `Input shaping against ringing`
  = `Компенсация вибраций против звона`
- `Klipper did not come back with {} within a minute.`
  = `Klipper не запустился с {} в течение минуты.`
- `Load cell estimate`
  = `Оценка по тензодатчику`
- `Local time for this screen`
  = `Местное время для этого экрана`
- `local.cfg sets the nozzle size; edit it there`
  = `Размер сопла задаётся в local.cfg; измените его там`
- `Measure the shape of the bed`
  = `Измерение формы стола`
- `Measures the frame's vibrations with the toolhead accelerometer and sets vibration compensation. The printer is loud for a few minutes.`
  = `Измеряет вибрации рамы акселерометром печатающей головки и настраивает компенсацию вибраций. Несколько минут принтер будет громко шуметь.`
- `Moves the nozzle over the purge box at the back. If the box isn't under the nozzle, move it with the arrows, then Accept.`
  = `Перемещает сопло к лотку для отходов сзади. Если лоток не под соплом, сдвиньте его стрелками и нажмите «Принять».`
- `New Patch`
  = `Ещё образец`
- `Nozzle Size`
  = `Размер сопла`
- `PID tuning for the nozzle and the bed`
  = `Настройка PID сопла и стола`
- `Printer Setup: Bed Mesh`
  = `Настройка принтера: сетка стола`
- `Printer Setup: Bed Soak`
  = `Настройка принтера: прогрев стола`
- `Printer Setup: Heater Tuning`
  = `Настройка принтера: нагреватели`
- `Printer Setup: IFS Tuning`
  = `Настройка принтера: IFS`
- `Printer Setup: Purge Box`
  = `Настройка принтера: лоток`
- `Printer Setup: Save`
  = `Настройка принтера: сохранение`
- `Printer Setup: Self-Check`
  = `Настройка принтера: самопроверка`
- `Printer Setup: Summary`
  = `Настройка принтера: итоги`
- `Printer Setup: Vibration Compensation`
  = `Настройка принтера: вибрации`
- `Printer Setup: Z Offset`
  = `Настройка принтера: смещение Z`
- `Prints a 30 mm test patch. While it prints, press Closer or Away until the lines are flat and just touch, then Accept. New Patch prints another patch beside it.`
  = `Печатает тестовый образец 30 мм. Во время печати нажимайте «Ближе» или «Дальше», пока линии не станут плоскими и не будут едва касаться друг друга, затем нажмите «Принять». «Ещё образец» печатает новый образец рядом.`
- `Purge box`
  = `Лоток для отходов`
- `Run Again`
  = `Ещё раз`
- `Run Setup Wizard`
  = `Запустить мастер настройки`
- `Save the results to the printer configuration`
  = `Сохранение результатов в конфигурацию принтера`
- `Saves the results to the printer configuration. Klipper restarts and the screen reconnects by itself.`
  = `Сохраняет результаты в конфигурацию принтера. Klipper перезапустится, и экран подключится снова сам.`
- `Saving setup results... Klipper will restart.`
  = `Сохранение результатов настройки... Klipper перезапустится.`
- `Saving... Klipper is restarting.`
  = `Сохранение... Klipper перезапускается.`
- `Self-check`
  = `Самопроверка`
- `Skip keeps the nozzle size Klipper runs with now.`
  = `«Пропустить» оставит размер сопла, с которым Klipper работает сейчас.`
- `Skip leaves this step out; you can run it later from Settings.`
  = `«Пропустить» пропускает этот шаг; его можно запустить позже из настроек.`
- `The nozzle fitted to the printer`
  = `Сопло, установленное на принтере`
- `The nozzle fitted to the printer. Line widths, purge lengths and the first-layer test use it. Change it later in Settings.`
  = `Сопло, установленное на принтере. От него зависят ширина линий, длина продувки и тест первого слоя. Изменить его можно позже в настройках.`
- `The results of the tuning so far. Check them, then Save.`
  = `Результаты настройки на данный момент. Проверьте их, затем сохраните.`
- `The results so far, before Save`
  = `Результаты на данный момент, до сохранения`
- `Time Zone`
  = `Часовой пояс`
- `Tunes filament swaps for every loaded IFS slot: the fastest reliable feed speed and the load and unload distances. Load filament into the slots you use first.`
  = `Настраивает смену филамента для каждого загруженного слота IFS: самую быструю надёжную скорость подачи и расстояния загрузки и выгрузки. Сначала загрузите филамент в нужные слоты.`
- `Tunes the heater control: the nozzle at 220 °C with the part fan running, then the bed at 60 °C. Takes 10 to 20 minutes; stay near the printer.`
  = `Настраивает управление нагревателями: сопло при 220 °C с включённым обдувом детали, затем стол при 60 °C. Занимает от 10 до 20 минут; оставайтесь рядом с принтером.`
- `Tunes the nozzle heater at 220 °C with the part fan running. The bed keeps its tuning. Takes 5 to 10 minutes; stay near the printer.`
  = `Настраивает нагреватель сопла при 220 °C с включённым обдувом детали. Настройка стола не меняется. Занимает от 5 до 10 минут; оставайтесь рядом с принтером.`
- `Used by the screen's clock and screensaver. You can change it later in Settings > Language & Time.`
  = `Используется часами экрана и заставкой. Изменить можно позже в разделе «Настройки > Язык и время».`
- `Vibration compensation`
  = `Компенсация вибраций`
- `Waiting for Klipper...`
  = `Ожидание Klipper...`
- `WARN`
  = `ВНИМАНИЕ`
- `Z offset`
  = `Смещение по Z`

</details>

<details><summary>IFS (filament unit) (52)</summary>

- `Auto-refill is off, so no backup spool takes over.`
  = `Автозамена выключена, поэтому резервная катушка не подключится.`
- `Auto-refill is on and {} is a backup, but it did not take over.`
  = `Автозамена включена и {} — резерв, но замена не произошла.`
- `Auto-refill is on, but no slot holds a backup for this spool.`
  = `Автозамена включена, но ни в одном слоте нет резерва для этой катушки.`
- `Auto-refill to {}`
  = `Автозамена: {}`
- `Changing filament`
  = `Смена филамента`
- `Cutting filament`
  = `Обрезка филамента`
- `Ejecting filament`
  = `Извлечение филамента`
- `Ejecting {}`
  = `Извлечение: {}`
- `Feed a spool up to the toolhead in advance`
  = `Заранее подать филамент к печатающей головке`
- `Feed speed`
  = `Скорость подачи`
- `Feeding filament`
  = `Подача филамента`
- `Feeding {}`
  = `Подача: {}`
- `Feeds the spool up to the toolhead sensor and backs it off, so a swap to it is quick`
  = `Подаёт филамент до датчика печатающей головки и немного отводит назад, чтобы смена на него была быстрой`
- `Finds the fastest reliable feed speed and each slot's distance to the toolhead sensor. Cuts and loads filament; takes several minutes.`
  = `Находит самую быструю надёжную скорость подачи и расстояние от каждого слота до датчика печатающей головки. Обрезает и загружает филамент; занимает несколько минут.`
- `Heating nozzle to {}°C`
  = `Нагрев сопла до {}°C`
- `Heating nozzle to {}°C ({}°C)`
  = `Нагрев сопла до {}°C ({}°C)`
- `HUB`
  = `ХАБ`
- `Homing the IFS`
  = `Парковка IFS`
- `IFS driver error`
  = `Ошибка драйвера IFS`
- `Last tune`
  = `Последняя настройка`
- `Load distance`
  = `Расстояние загрузки`
- `Loaded in the toolhead`
  = `Загружен в печатающую головку`
- `Loading filament`
  = `Загрузка филамента`
- `Loading {}`
  = `Загрузка: {}`
- `No filament in this slot`
  = `В этом слоте нет филамента`
- `Not tuned`
  = `Не настроено`
- `Pre-feed slot 1`
  = `Предзагрузка слота 1`
- `Pre-feed slot 2`
  = `Предзагрузка слота 2`
- `Pre-feed slot 3`
  = `Предзагрузка слота 3`
- `Pre-feed slot 4`
  = `Предзагрузка слота 4`
- `Pre-feeding filament`
  = `Предзагрузка филамента`
- `Pre-feeding {}`
  = `Предзагрузка: {}`
- `Priming the nozzle`
  = `Подготовка сопла`
- `Retracting filament`
  = `Втягивание филамента`
- `Retracting {}`
  = `Втягивание: {}`
- `SELECTOR`
  = `СЕЛЕКТОР`
- `Selecting a slot`
  = `Выбор слота`
- `Selecting the slot`
  = `Выбор слота`
- `Selecting {}`
  = `Выбор: {}`
- `Swap to {}`
  = `Смена: {}`
- `Swapping filament`
  = `Смена филамента`
- `The IFS is busy`
  = `IFS занят`
- `Tune IFS`
  = `Настроить IFS`
- `Tune the IFS feed speed and load distances`
  = `Настройка скорости подачи и расстояний загрузки IFS`
- `Tuning`
  = `Настройка`
- `Tuning is running`
  = `Идёт настройка`
- `Tuning the IFS`
  = `Настройка IFS`
- `Tuning {}`
  = `Настройка: {}`
- `Unload distance`
  = `Расстояние выгрузки`
- `Unloading {}`
  = `Выгрузка: {}`
- `Which slot each tool of a print uses`
  = `Какой слот использует каждый инструмент печати`
- `Which spool auto-refill takes over with`
  = `Какой катушкой автозамена продолжает печать`

</details>

<details><summary>Auto-refill (30)</summary>

- `Any colour`
  = `Любой цвет`
- `Auto colour`
  = `Авто по цвету`
- `Auto-refill`
  = `Автозамена`
- `Auto-Refill`
  = `Автозамена`
- `Auto-Refill colour match`
  = `Автозамена: подбор цвета`
- `BACKUPS`
  = `РЕЗЕРВЫ`
- `backups for slot {}`
  = `резервы для слотов: {}`
- `Colour match`
  = `Подбор цвета`
- `Exact`
  = `Точный`
- `Exact colour`
  = `Точный цвет`
- `Exact: the same colour code. Similar: close shades. Any colour: the same material is enough.`
  = `Точный: тот же код цвета. Похожий: близкие оттенки. Любой цвет: достаточно того же материала.`
- `Filament slots`
  = `Слоты филамента`
- `material not set`
  = `материал не указан`
- `no backup`
  = `нет резерва`
- `No backup spool`
  = `Нет резервной катушки`
- `no backup spools`
  = `нет резервных катушек`
- `No backups: put the same filament in another slot and set its material and colour on the Filament screen.`
  = `Нет резервов: вставьте тот же филамент в другой слот и укажите его материал и цвет на экране «Филамент».`
- `No filament in the IFS`
  = `В IFS нет филамента`
- `Similar`
  = `Похожий`
- `Similar colour`
  = `Похожий цвет`
- `Slot per file`
  = `Слот из файла`
- `Slot per file: the file's own slot for each tool. Auto colour: each tool uses the loaded slot with the same material and the nearest colour, so a file made before can still print.`
  = `Слот из файла: для каждого инструмента — слот, указанный в файле. Авто по цвету: каждый инструмент берёт загруженный слот с тем же материалом и ближайшим цветом, поэтому можно напечатать и ранее подготовленный файл.`
- `Slot {}`
  = `Слот {}`
- `Slot {} · {} — {}`
  = `Слот {} · {} — {}`
- `Slots {}`
  = `Слоты {}`
- `The filament slots aren't available yet`
  = `Слоты филамента пока недоступны`
- `To add one, put the same filament in a free slot and set its material and colour; it is fed in when it's needed.`
  = `Чтобы добавить резерв, вставьте тот же филамент в свободный слот и укажите его материал и цвет; он будет подан, когда понадобится.`
- `Tool to slot`
  = `Назначение слотов`
- `Turn off auto-refill`
  = `Выключить автозамену`
- `When a spool runs out mid-print, the printer switches to a slot with the same material and colour and carries on.`
  = `Если катушка заканчивается во время печати, принтер переключается на слот с тем же материалом и цветом и продолжает печать.`

</details>

<details><summary>Bed heat soak (32)</summary>

- `, corners {:+.3f} to {:+.3f}`
  = `, углы от {:+.3f} до {:+.3f}`
- `, not fully settled`
  = `, не до конца стабилизировался`
- `After a cold start the bed keeps moving for minutes after it reaches its temperature. The print start waits this long before it checks Z; the purge counts toward it.`
  = `После холодного старта стол ещё несколько минут смещается после достижения температуры. Перед проверкой Z старт печати ждёт столько времени; продувка входит в это время.`
- `Bed Heat Soak`
  = `Прогрев стола`
- `Bed heat soak before the Z check`
  = `Прогрев стола перед проверкой Z`
- `Bed soak at {} °C calibrated.`
  = `Прогрев стола при {} °C откалиброван.`
- `Bed temperature`
  = `Температура стола`
- `CALIBRATE`
  = `КАЛИБРОВАТЬ`
- `Calibrate the bed soak at {} °C?`
  = `Откалибровать прогрев стола при {} °C?`
- `CALIBRATED`
  = `ОТКАЛИБРОВАНО`
- `CALIBRATING`
  = `ИДЁТ КАЛИБРОВКА`
- `Calibration stopped. Heaters off, nothing saved.`
  = `Калибровка остановлена. Нагреватели выключены, ничего не сохранено.`
- `Can't calibrate now`
  = `Сейчас калибровка невозможна`
- `Homing and heating...`
  = `Парковка и нагрев...`
- `Let the bed cool below {} °C (now {} °C). The calibration measures from a cold bed.`
  = `Дайте столу остыть ниже {} °C (сейчас {} °C). Калибровка измеряет от холодного стола.`
- `Measures how long the bed keeps moving at that temperature. Takes 20-35 minutes; the bed must be empty and below 40 °C.`
  = `Измеряет, как долго стол смещается при этой температуре. Занимает 20-35 минут; стол должен быть пустым и холоднее 40 °C.`
- `No calibration during a print`
  = `Калибровка во время печати недоступна`
- `No readings yet: the first comes once the bed is hot.`
  = `Измерений пока нет: первое появится, когда стол нагреется.`
- `not calibrated`
  = `не откалибровано`
- `Not calibrated yet: 3 s per degree the bed heats, at most 10 minutes`
  = `Ещё не откалибровано: 3 с на каждый градус нагрева стола, не более 10 минут`
- `Since the bed was hot, one round a minute:`
  = `С момента нагрева стола, один замер в минуту:`
- `Stop the calibration?`
  = `Остановить калибровку?`
- `Stopping: heaters off...`
  = `Остановка: нагреватели выключаются...`
- `The bed is still warm`
  = `Стол ещё тёплый`
- `The bed must be empty. The printer homes, heats the nozzle and bed and probes the bed every minute; this takes 20-35 minutes. Continue?`
  = `Стол должен быть пустым. Принтер паркуется, нагревает сопло и стол и каждую минуту измеряет стол; это занимает 20-35 минут. Продолжить?`
- `The bed soak can't be calibrated during a print.`
  = `Прогрев стола нельзя калибровать во время печати.`
- `The calibration ended; the list shows what was saved.`
  = `Калибровка завершена; в списке показано, что сохранено.`
- `The heaters switch off and nothing is saved.`
  = `Нагреватели выключатся, ничего не сохранится.`
- `The temperature to measure, from a cold bed`
  = `Температура для измерения, начиная с холодного стола`
- `This printer can't stop the calibration from the screen; use the emergency stop.`
  = `Этот принтер не может остановить калибровку с экрана; используйте аварийную остановку.`
- `{}  centre {:+.3f} mm`
  = `{}  центр {:+.3f} мм`
- `{} °C — {} (centre moved {:.2f} mm)`
  = `{} °C — {} (центр сместился на {:.2f} мм)`

</details>

<details><summary>Plugins (20)</summary>

- `All catalog plugins are installed`
  = `Все плагины из каталога установлены`
- `AVAILABLE`
  = `ДОСТУПНЫЕ`
- `Built-in`
  = `Встроенный`
- `Deletes the plugin from the printer.`
  = `Удаляет плагин с принтера.`
- `Downloads the plugin and turns it on. Klipper restarts when it is installed.`
  = `Загружает плагин и включает его. После установки Klipper перезапускается.`
- `Install {}?`
  = `Установить {}?`
- `INSTALLED`
  = `УСТАНОВЛЕННЫЕ`
- `Installing {}...`
  = `Установка {}...`
- `Klipper restarts to apply this. Continue?`
  = `Для применения Klipper перезапустится. Продолжить?`
- `Needs a newer Kiln OS`
  = `Нужна более новая Kiln OS`
- `Plugins can't be changed during a print`
  = `Во время печати плагины изменить нельзя`
- `Remove {}?`
  = `Удалить {}?`
- `STATUS`
  = `СОСТОЯНИЕ`
- `Turn off {}?`
  = `Выключить {}?`
- `Turn on {}?`
  = `Включить {}?`
- `Turns the plugin off and deletes it from the printer. Klipper restarts.`
  = `Выключает плагин и удаляет его с принтера. Klipper перезапускается.`
- `Update {}?`
  = `Обновить {}?`
- `Updating {}...`
  = `Обновление {}...`
- `When there is a new version, Klipper restarts to load it.`
  = `Когда выходит новая версия, Klipper перезапускается, чтобы загрузить её.`
- `Working on {}...`
  = `Обработка {}...`

</details>

<details><summary>Printer sounds (9)</summary>

- `Filament Auto-Refill`
  = `Автозамена филамента`
- `Power On`
  = `Включение`
- `Print Cancelled`
  = `Печать отменена`
- `Print Finished`
  = `Печать завершена`
- `Print Started`
  = `Печать начата`
- `PRINTER SOUNDS`
  = `ЗВУКИ ПРИНТЕРА`
- `Printer Sounds`
  = `Звуки принтера`
- `Printer Volume`
  = `Громкость принтера`
- `Sounds the printer plays on print events`
  = `Звуки принтера при событиях печати`

</details>

<details><summary>Nozzle size (7)</summary>

- `Change the nozzle size to {}?`
  = `Изменить размер сопла на {}?`
- `Changing the nozzle size... Klipper will restart.`
  = `Смена размера сопла... Klipper перезапустится.`
- `Nozzle changed to {}`
  = `Сопло изменено на {}`
- `Run the hotend PID tune and the first-layer Z offset test now? (The bed doesn't need retuning.)`
  = `Запустить сейчас настройку PID хотенда и тест смещения по Z на первом слое? (Стол перенастраивать не нужно.)`
- `The nozzle fitted to the printer. Line widths, purge lengths and the first-layer test use it.`
  = `Сопло, установленное на принтере. От него зависят ширина линий, длина продувки и тест первого слоя.`
- `The nozzle size can't change during a print`
  = `Размер сопла нельзя изменить во время печати`
- `{}, set in local.cfg`
  = `{}, задано в local.cfg`

</details>

<details><summary>Chamber light and screen sleep (2)</summary>

- `Chamber light off when the screen sleeps`
  = `Подсветка камеры выключается, когда экран засыпает`
- `Chamber light turns off when the screen sleeps, but stays on during a print`
  = `Подсветка камеры выключается, когда экран засыпает, но остаётся включённой во время печати`

</details>

<details><summary>Settings menu entries and home screen tiles (5)</summary>

- `Move the trash bin the nozzle purges into`
  = `Переместить лоток, в который продувается сопло`
- `Not available while printing`
  = `Недоступно во время печати`
- `Printer add-ons: switch on or off, install, update`
  = `Дополнения принтера: включение, установка, обновление`
- `Purge Box`
  = `Лоток для отходов`
- `Self-check, PID, bed mesh, vibration, IFS, Z offset`
  = `Самопроверка, PID, сетка стола, вибрации, IFS, смещение по Z`

</details>

<details><summary>Settings > System: Boot into recovery (6)</summary>

- `Boot into recovery`
  = `Загрузить систему восстановления`
- `Boot into recovery?`
  = `Загрузить систему восстановления?`
- `Can't boot into recovery: {}`
  = `Не удалось загрузить систему восстановления: {}`
- `Restart into the recovery OS (install an update from a USB stick or the web page on port 8080)`
  = `Перезапуск в систему восстановления (установка обновления с USB-флешки или через веб-страницу на порту 8080)`
- `Restarting into the recovery OS...`
  = `Перезапуск в систему восстановления...`
- `The printer restarts into the recovery OS, where it can't print. To come back, tap Boot main OS on its screen.`
  = `Принтер перезапустится в систему восстановления, где печать недоступна. Чтобы вернуться, нажмите на её экране «Запустить ОС».`

</details>

<details><summary>The IFS in messages that said AMS (5)</summary>

- `IFS not detected`
  = `IFS не обнаружен`
- `IFS Active: `
  = `IFS активен: `
- `Bypass is active, but this print uses IFS slots. ...`, `The toolhead has filament but no IFS slot reports it loaded. ...` (two texts)
  = the Russian of the same texts with AMS, which already said IFS

</details>

<details><summary>Settings > System: Log detail (4)</summary>

- `Log detail`
  = `Детализация журнала`
- `Short`
  = `Краткий`
- `Extended`
  = `Подробный`
- `Short: warnings and errors, and Klipper's statistics once a minute. Extended: everything, for troubleshooting; the logs fill faster.`
  = `Краткий: предупреждения и ошибки, статистика Klipper раз в минуту. Подробный: всё, для поиска неисправностей; журналы заполняются быстрее.`

</details>

<details><summary>Reboot and Shutdown: Advanced and the home screen tile (6)</summary>

- `Restart the printer?`
  = `Перезагрузить принтер?`
- `Shut down the printer?`
  = `Выключить принтер?`
- `The printer can't be used until it has started again.`
  = `Принтером нельзя пользоваться, пока он не запустится снова.`
- `The printer stays off until you switch it on again.`
  = `Принтер останется выключенным, пока вы снова его не включите.`
- `Can't restart the printer: {}`
  = `Не удалось перезагрузить принтер: {}`
- `Can't shut down the printer: {}`
  = `Не удалось выключить принтер: {}`

</details>

<details><summary>Settings > System: Return to Flashforge firmware (5)</summary>

- `Can't return to Flashforge firmware: {}`
  = `Не удалось вернуть прошивку Flashforge: {}`
- `Restart into the recovery OS to put Flashforge's own firmware back`
  = `Перезапуск в систему восстановления, чтобы вернуть стоковую прошивку Flashforge`
- `Return to Flashforge firmware`
  = `Вернуть прошивку Flashforge`
- `Return to Flashforge firmware?`
  = `Вернуть прошивку Flashforge?`
- `The printer restarts into the recovery OS. There, check what it found and tap Return to Flashforge to start. Nothing is changed before that tap.`
  = `Принтер перезапустится в систему восстановления. Там проверьте, что она нашла, и нажмите «Вернуть Flashforge», чтобы начать. До этого нажатия ничего не меняется.`

  «Вернуть Flashforge» is the recovery screen's button (`rs_go`); keep the two the same.

</details>

<details><summary>Settings > System: Extended memory (8)</summary>

- `Extended memory`
  = `Расширенная память`
- `Use all 512 MiB. Not needed; off by default. Takes effect after a restart.`
  = `Использовать все 512 МБ. Не обязательно; по умолчанию выключено. Вступает в силу после перезагрузки.`
- `Extended memory changes at the next start.`
  = `Изменение расширенной памяти вступит в силу при следующем запуске.`
- `Extended memory was turned off: the printer didn't finish starting with it.`
  = `Расширенная память выключена: с ней принтер не смог завершить запуск.`
- `Needs a boot loader update to take effect.`
  = `Вступит в силу после обновления загрузчика.`
- `Extended memory available`
  = `Доступна расширенная память`
- `This printer has 512 MiB of memory. Kiln OS uses 256 MiB by default, the same on every AD5X. You can switch Extended memory on in Settings > System. It isn't needed; it is off by default.`
  = `В принтере 512 МБ, а Kiln OS на всех AD5X по умолчанию использует 256 МБ. Расширенную память можно включить в Настройки > Система. Это не обязательно; по умолчанию она выключена.`
- `Restart now?`
  = `Перезагрузить сейчас?`

</details>

<details><summary>Settings > Devices: IFS firmware (35)</summary>

- `IFS firmware`
  = `Прошивка IFS`
- `Stock`
  = `Стоковая`
- `Switch to Stock`
  = `Перейти на стоковую`
- `Switch to Klipper`
  = `Перейти на Klipper`
- `Switch`
  = `Сменить`
- `Switch the IFS to stock firmware?`
  = `Перевести IFS на стоковую прошивку?`
- `Switch the IFS to Klipper firmware?`
  = `Перевести IFS на прошивку Klipper?`
- `Writes Flashforge's firmware from this printer's own backup. Klipper stops for 1 to 4 minutes. Plugins that need Klipper firmware on the IFS (Happy Hare) are skipped until you switch back.`
  = `Будет записана прошивка Flashforge из резервной копии этого принтера. Klipper остановится на 1–4 минуты. Плагины, которым нужна прошивка Klipper на IFS (Happy Hare), не будут запускаться, пока вы не переключите IFS обратно.`
- `Writes the Klipper firmware that comes with Kiln OS. Klipper stops for 1 to 4 minutes.`
  = `Будет записана прошивка Klipper, которая входит в Kiln OS. Klipper остановится на 1–4 минуты.`
- `Switching IFS firmware…`
  = `Смена прошивки IFS…`
- `Don't switch the printer off.`
  = `Не выключайте принтер.`
- `Stopping Klipper…`
  = `Остановка Klipper…`
- `Writing…`
  = `Запись…`
- `Unplug the IFS cable and plug it back in`
  = `Отключите кабель IFS и подключите его снова`
- `Checking the IFS…`
  = `Проверка IFS…`
- `Starting Klipper…`
  = `Запуск Klipper…`
- `IFS firmware switched`
  = `Прошивка IFS сменена`
- `IFS firmware switch refused`
  = `Смена прошивки IFS отклонена`
- `IFS firmware switch failed`
  = `Не удалось сменить прошивку IFS`
- `IFS firmware switch`
  = `Смена прошивки IFS`
- `IFS on stock firmware.`
  = `IFS работает на стоковой прошивке.`
- `IFS on Klipper firmware.`
  = `IFS работает на прошивке Klipper.`
- `IFS on stock firmware: {} answers.`
  = `IFS работает на стоковой прошивке: отвечает версия {}.`
- `IFS on Klipper firmware: {} answers.`
  = `IFS работает на прошивке Klipper: отвечает версия {}.`
- `Kiln's IFS driver runs it. Plugins that need Klipper firmware on the IFS are skipped until you switch back.`
  = `Им управляет драйвер IFS в Kiln. Плагины, которым нужна прошивка Klipper на IFS, не запускаются, пока вы не переключите IFS обратно.`
- `Plugins that need it run again.`
  = `Плагины, которым она нужна, снова запускаются.`
- `No result. See /data/ad5x/kiln-log/agent.log.`
  = `Нет результата. См. /data/ad5x/kiln-log/agent.log.`
- `Waiting for Klipper…`
  = `Ожидание Klipper…`
- `The IFS runs Klipper firmware.`
  = `IFS работает на прошивке Klipper.`
- `The IFS runs Flashforge's firmware.`
  = `IFS работает на прошивке Flashforge.`
- `The IFS doesn't answer as either firmware. Switch it to one of them.`
  = `IFS не отвечает ни на одной из прошивок. Переведите его на одну из них.`
- `Last switch: {}`
  = `Последняя смена прошивки: {}`
- `Can't switch during a print.`
  = `Во время печати прошивку сменить нельзя.`
- `Klipper did not start again. See klippy.log and ad5x-mcu status.`
  = `Klipper не запустился снова. См. klippy.log и ad5x-mcu status.`
- `The switch did not finish. See /data/ad5x/kiln-log/agent.log.`
  = `Смена прошивки не завершилась. См. /data/ad5x/kiln-log/agent.log.`

</details>

<details><summary>Settings > About: eMMC (3)</summary>

The row reads, for example, `eMMC: A31M8C (производитель 0xEC), PRV 0x30, 58.2 ГБ`. The name and `PRV` stay as they are.

- `eMMC`
  = `eMMC`
- ` (maker 0x{:02X})`
  = ` (производитель 0x{:02X})`
- `, {:.1f} GiB`
  = `, {:.1f} ГБ`

</details>

<details><summary>Settings > About: Processor (7)</summary>

The row reads, for example, `X2600E, 256 МБ DDR3, SoC ID 0x18000, ядро 0.0`. Chip names, `DDR2`/`DDR3` and
`SoC ID` stay as they are. Without the eFuse (6.6 kernel) it reads `X2600, 256 МБ, вариант неизвестен`.

- `Processor`
  = `Процессор`
- `{} MiB {}`
  = `{} МБ {}`
- `, {} MiB`
  = `, {} МБ`
- `, core {}`
  = `, ядро {}`
- `{}, size unknown`
  = `{}, размер неизвестен`
- `X2600, variant unknown ({})`
  = `X2600, вариант неизвестен ({})`
- `X2600{}, variant unknown{}`
  = `X2600{}, вариант неизвестен{}`

</details>

<details><summary>Setup wizard: Filament step, a running step, Z offset test (52)</summary>

The last block of `helixscreen-ru.yml` (`# Setup wizard: the filament step, ...`). The action lines (Heating, Probing the bed, ...) show one at a time above the status line while a step runs, so they should be short; the temperatures line reads, for example, `Сопло 180/240 °C  ·  Стол 58/70 °C  ·  1:05`.

- `Set the material in each slot with filament; the tests heat to it. Auto finds which slot is in the toolhead and unloads it, or pick the slot yourself.`
  = `Укажите материал в каждом слоте с филаментом: тесты нагревают сопло под него. «Авто» само находит слот, который в печатающей головке, и выгружает его; можно выбрать слот и вручную.`
- `Toolhead: slot {} was in it, now unloaded`
  = `Печатающая головка: в ней был слот {}, теперь выгружен`
- `Toolhead: slot {}`
  = `Печатающая головка: слот {}`
- `Toolhead: slot {}, {}`
  = `Печатающая головка: слот {}, {}`
- `Toolhead: filament from an unknown slot`
  = `Печатающая головка: филамент из неизвестного слота`
- `Toolhead: empty`
  = `Печатающая головка: пусто`
- `Checking the printer`
  = `Проверка принтера`
- `Testing the fans`
  = `Проверка вентиляторов`
- `Testing the heaters`
  = `Проверка нагревателей`
- `Tuning the nozzle heater`
  = `Настройка нагревателя сопла`
- `Tuning the bed heater`
  = `Настройка нагревателя стола`
- `Cleaning the nozzle`
  = `Очистка сопла`
- `Probing the bed`
  = `Проверка стола датчиком`
- `Measuring vibrations on X`
  = `Измерение вибраций по X`
- `Measuring vibrations on Y`
  = `Измерение вибраций по Y`
- `Setting the slot materials`
  = `Сохранение материалов слотов`
- `Finding the slot in the toolhead`
  = `Поиск слота в печатающей головке`
- `Moving to the purge box`
  = `Перемещение к лотку для отходов`
- `Loading slot {}`
  = `Загрузка слота {}`
- `Unloading slot {}`
  = `Выгрузка слота {}`
- `Estimating the Z offset`
  = `Оценка смещения по Z`
- `Preparing the test print`
  = `Подготовка тестовой печати`
- `Purging the nozzle`
  = `Продувка сопла`
- `Printing the test patch`
  = `Печать тестового образца`
- `Printing test patch {}`
  = `Печать тестового образца {}`
- `Waiting for you`
  = `Ожидает вашего действия`
- `Saving`
  = `Сохранение`
- `Letting the bed cool`
  = `Остывание стола`
- `Calibrating the bed soak`
  = `Калибровка прогрева стола`
- `Slot {}, {}, {}/{} °C`
  = `Слот {}, {}, {}/{} °C`
- `{}, {}/{} °C`
  = `{}, {}/{} °C`
- `No temperatures for {}: using PLA temperatures`
  = `Для {} нет температур: используются температуры PLA`
- `Material unknown: using PLA temperatures`
  = `Материал неизвестен: используются температуры PLA`
- `Abort and set it in the Filament step if this is wrong.`
  = `Если это неверно, прервите и укажите материал на шаге «Филамент».`
- `Auto (find it)`
  = `Авто (найти)`
- `None (empty)`
  = `Нет (пусто)`
- `The IFS slots aren't known yet.`
  = `Слоты IFS пока неизвестны.`
- `Printer Setup: Filament`
  = `Настройка принтера: филамент`
- `The material in each slot and the slot in the toolhead`
  = `Материал в слотах и слот в печатающей головке`
- `Filament in the toolhead`
  = `Филамент в печатающей головке`
- `Remove the test print from the bed`
  = `Уберите тестовую печать со стола`
- `The Z offset is saved. Take the test print off the bed so the next steps don't probe or print on it, then tap Done.`
  = `Смещение по Z сохранено. Снимите тестовую печать со стола, чтобы следующие шаги не проверяли и не печатали по ней, затем нажмите «Готово».`
- `No slot cleared the toolhead. Cut the filament at the toolhead if it isn't cut, pull it out at the top by hand, then tap Retry.`
  = `Ни один слот не освободил печатающую головку. Обрежьте филамент у головки, если он не обрезан, вытяните его сверху рукой и нажмите «Повторить».`
- `Remove the test print from the bed before you retry.`
  = `Перед повтором уберите тестовую печать со стола.`
- `Use the filament in the toolhead as it is`
  = `Использовать филамент в печатающей головке как есть`
- `Toolhead: strand in the tube, slot unknown`
  = `Печатающая головка: филамент остался в трубке, слот неизвестен`
- `Toolhead: filament kept as it is`
  = `Печатающая головка: филамент оставлен как есть`
- `Slot {} · {}`
  = `Слот {} · {}`
- `A strand is still in the tube: name the slot first`
  = `В трубке остался филамент: сначала укажите его слот`
- `Which slot is in the toolhead?`
  = `Какой слот в печатающей головке?`
- `Kiln can't tell which slot's filament is in the toolhead. Look at the tubes: tap the slot whose filament goes into the toolhead. Nothing is fed until you choose.`
  = `Kiln не может определить, филамент какого слота в печатающей головке. Посмотрите на трубки и нажмите слот, филамент которого идёт в печатающую головку. Пока вы не выберете, ничего не подаётся.`
- `I pulled it out by hand`
  = `Филамент вытянут вручную`
- `Run the setup wizard?`
  = `Запустить мастер настройки?`
- `Kiln OS is installed again and kept your settings. Flashforge's firmware ran in between and may have changed the filament, the Z offset or the boards. The setup wizard checks and tunes the printer again; every step can be skipped.`
  = `Kiln OS установлена снова, ваши настройки сохранены. До этого работала прошивка Flashforge: она могла изменить филамент, смещение по Z или прошивку плат. Мастер настройки снова проверит и настроит принтер, любой шаг можно пропустить.`
- `Boot loader update ready`
  = `Готово обновление загрузчика`
- `A boot loader update is ready. To install it: Settings > System > Boot into recovery > Reboot / Power > Update Kiln's boot loader. Nothing is written until you start it there.`
  = `Готово обновление загрузчика. Чтобы установить его: Настройки > Система > Загрузить систему восстановления > Питание > Обновить загрузчик Kiln. Пока вы не запустите обновление там, ничего не записывается.`
- `Kiln's own boot loader`
  = `Собственный загрузчик Kiln`
- `Kiln OS has its own boot loader for this printer. To install it: Settings > System > Boot into recovery > Reboot / Power > Install Kiln's boot loader. Read the boot loader guide first; it explains the risk and the rescue stick: github.com/djvalic/kiln-os/blob/main/docs/own-boot-loader.md`
  = `У Kiln OS есть собственный загрузчик для этого принтера. Чтобы установить его: Настройки > Система > Загрузить систему восстановления > Питание > Установить загрузчик Kiln. Сначала прочитайте руководство по загрузчику, в нём описаны риск и флешка для восстановления: github.com/djvalic/kiln-os/blob/main/docs/own-boot-loader.md`

</details>

## 6. Recovery screen (recovery-ui/i18n/ru.txt)

The recovery screen is Kiln OS's rescue system. It uses the touch screen's language setting. Its strings are in
[recovery-ui/i18n/en.txt](../../recovery-ui/i18n/en.txt) (English) and [recovery-ui/i18n/ru.txt](../../recovery-ui/i18n/ru.txt)
(Russian). I wrote a first Russian version of all 305 lines; please check it and correct `ru.txt` directly:
each line is the id, one TAB, then the text. The rules are at the top of `en.txt`:

- keep the id; write the Russian after the TAB (keep the TAB, not spaces)
- keep `%s`, `%d`, `%u` in the same order and number; `%%` is a percent sign
- `\n` is a line break
- keep file paths and command names (`/data/ad5x/...`, `ad5x-update`, `SWUpdate`) as they are
- leave out the icons and "Kiln OS": the screen adds them (`recovery_title` is shown after "Kiln OS")
- the screen is small: keep a text about as long as the English, buttons especially
- the recovery font holds the whole Russian alphabet and the other characters the texts use; if you add a new sign, that's fine, I regenerate the font

The lines I am least sure of:

- `recovery_row` = `Версия`: the row shows the recovery's release number. `Восстановление` does not fit the 120 px label.
- `update_one` / `update_many` = `обновление` / `обновл.`: the screen has only these two forms after a number, so the
  second is shortened to fit both 2-4 (обновления) and 5+ (обновлений).
- Stock firmware = `стоковая прошивка`, the same word as on the touch screen (IFS firmware switch, Return to Flashforge
  firmware); the boot loader is `стоковый загрузчик`. Until patch 0080 this screen said `родная прошивка`.
- Recovery = `Восстановление`, and Restore from a backup = `Восстановить` / `Восстановление копии`.
- Dry run = `Проба`, and `Boot main OS` = `Запустить ОС`: the long forms (`Пробный запуск`, `Запустить основную ОС`) do
  not fit their buttons.

### Buttons and common words

- `back`: `Back`
  = `Назад`
- `cancel`: `Cancel`
  = `Отмена`
- `continue`: `Continue`
  = `Продолжить`
- `try`: `Try`
  = `Попробовать`
- `done`: `Done`
  = `Готово`
- `stop`: `Stop`
  = `Стоп`
- `check`: `Check`
  = `Проверить`
- `rescan`: `Rescan`
  = `Обновить`
- `install`: `Install`
  = `Установить`
- `restore`: `Restore`
  = `Восстановить`
- `eject`: `Eject`
  = `Извлечь`
- `mount`: `Mount`
  = `Подключить`
- `reboot`: `Reboot`
  = `Перезагрузить`
- `shut_down`: `Shut down`
  = `Выключить`
- `power`: `Power`
  = `Питание`
- `boot_main_os`: `Boot main OS`
  = `Запустить ОС`
- `install_now`: `Install now`
  = `Установить`
- `restore_now`: `Restore now`
  = `Восстановить`
- `restore_stock`: `Restore stock`
  = `Вернуть стоковую`
- `restore_stock_fw_btn`: `Restore stock firmware…`
  = `Вернуть стоковую прошивку…`
- `start_backup`: `Start backup`
  = `Начать копирование`
- `dry_run`: `Dry run`
  = `Проба`
- `are_you_sure`: `Are you sure?`
  = `Вы уверены?`
- `step_1_of_2`: `Step 1 of 2`
  = `Шаг 1 из 2`
- `step_2_of_2`: `Step 2 of 2: last chance to cancel`
  = `Шаг 2 из 2: последняя возможность отменить`
- `wait_n_s`: `Wait %d s`
  = `Подождите %d с`

### Home screen and status

- `no_network`: `no network`
  = `нет сети`
- `not_running`: `not running`
  = `не запущен`
- `no_network_home`: `No network (Ethernet or Wi-Fi)`
  = `Нет сети (Ethernet или Wi-Fi)`
- `ssh_not_running`: `SSH not running`
  = `SSH не запущен`
- `recovery_title`: `—  Recovery`
  = `—  Восстановление`
- `busy`: `busy`
  = `занят`
- `swu_ready`: `SWUpdate ready`
  = `SWUpdate готов`
- `swu_not_running`: `SWUpdate not running`
  = `SWUpdate не запущен`
- `boot_flag_unreadable`: `boot flag unreadable`
  = `флаг загрузки не читается`
- `next_main`: `next start: main OS`
  = `следующий запуск: основная ОС`
- `next_recovery`: `next start: recovery`
  = `следующий запуск: восстановление`
- `home_slot`: `Main OS (slot B): %s   ·   %s`
  = `Основная ОС (слот B): %s   ·   %s`
- `slot_installed`: `installed`
  = `установлена`
- `slot_not_found`: `not found`
  = `не найдена`
- `slot_empty`: `empty`
  = `пусто`
- `slot_unknown`: `unknown`
  = `неизвестно`
- `home_trace`: `Main OS last start got to: %s`
  = `Последний запуск основной ОС дошёл до: %s`
- `home_no_trace`: `Main OS last start: no trace`
  = `Последний запуск основной ОС: нет записи`
- `home_last_update`: `Last update: %s`
  = `Последнее обновление: %s`
- `home_no_update`: `Last update: none recorded`
  = `Последнее обновление: нет записи`

### Main menu

- `back_up`: `Back up`
  = `Резервная копия`
- `install_update`: `Install update`
  = `Обновление`
- `network_ssh`: `Network / SSH`
  = `Сеть / SSH`
- `logs`: `Logs`
  = `Журналы`
- `reboot_power`: `Reboot / Power`
  = `Питание`
- `update`: `Update`
  = `Обновление`
- `update_from_browser`: `Update from browser`
  = `Обновление из браузера`

### Boot the main OS

- `boot_main_what`: `Checking slot B, setting the boot flag, restarting`
  = `Проверка слота B, установка флага загрузки, перезапуск`
- `boot_main_q`: `Boot the main OS?`
  = `Запустить основную ОС?`
- `boot_main_text`: `The printer restarts into the main OS (slot B). If it doesn't finish starting, the next start comes back here.`
  = `Принтер перезапустится в основную ОС (слот B). Если она не запустится до конца, следующий запуск вернётся сюда.`
- `no_main_q`: `No main OS found?`
  = `Основная ОС не найдена?`
- `no_main_text`: `Slot B doesn't look like it holds a system. ad5x-boot-main checks it again and refuses if it is empty. Try anyway?`
  = `Похоже, в слоте B нет системы. ad5x-boot-main проверит его ещё раз и откажется, если он пуст. Всё равно попробовать?`

### Install an update

- `installing_update`: `Installing update`
  = `Установка обновления`
- `install_q`: `Install update?`
  = `Установить обновление?`
- `install_q_text`: `Install %s into the main OS slot (B)? The system there now is replaced.`
  = `Установить %s в слот основной ОС (B)? Система, которая там сейчас, будет заменена.`
- `install_q_text2`: `SWUpdate checks the signature, then writes slot B. Don't switch the printer off until it says done.`
  = `SWUpdate проверит подпись, затем запишет слот B. Не выключайте принтер, пока не появится «готово».`
- `checking_update`: `Checking update`
  = `Проверка обновления`
- `no_update_fmt`: `No .swu or .zip update found.\nCopy one to %s or to the top folder of a USB stick, or upload it from a browser.`
  = `Обновление .swu или .zip не найдено.\nСкопируйте его в %s или в корень USB-накопителя либо загрузите из браузера.`
- `upload_hint`: `Or upload from a browser:  http://%s:8080`
  = `Или загрузите из браузера:  http://%s:8080`
- `upload_hint_nonet`: `Or upload from a browser on port 8080 (no network yet)`
  = `Или загрузите из браузера на порт 8080 (сети пока нет)`

### USB stick

- `mounting`: `Mounting`
  = `Подключение`
- `ejecting`: `Ejecting`
  = `Извлечение`
- `usb_busy`: `%s the USB stick…`
  = `%s USB-накопителя…`
- `usb_mounted`: `%s (%s), %s free`
  = `%s (%s), свободно %s`
- `usb_not_mounted`: `USB stick %s not mounted`
  = `USB-накопитель %s не подключён`
- `usb_none`: `No USB stick: insert one (FAT32, exFAT or ext4)`
  = `Нет USB-накопителя: вставьте его (FAT32, exFAT или ext4)`
- `usb_no_stick`: `USB: no stick mounted`
  = `USB: накопитель не подключён`

### Back up to USB

- `bk_dest_none`: `Destination: a USB stick (none mounted)`
  = `Куда: USB-накопитель (не подключён)`
- `bk_dest`: `Destination:  %s/%s<date>-<n>/`
  = `Куда:  %s/%s<дата>-<n>/`
- `backup_dry_run`: `Backup (dry run)`
  = `Копирование (проба)`
- `backing_up`: `Backing up`
  = `Резервное копирование`
- `back_up_title`: `Back up to USB`
  = `Резервная копия на USB`
- `backup_text`: `Copies the eMMC to the stick: boot area, both slots, boot flag and usershare, each read back and checked. Nothing on the printer is changed.`
  = `Копирует eMMC на накопитель: загрузочную область, оба слота, флаг загрузки и usershare, каждую часть читает обратно и проверяет. На принтере ничего не меняется.`
- `also_userdata`: `Also userdata (5.8 GB, slow)`
  = `И userdata (5,8 ГБ, долго)`

### Restore from USB

- `restore_title`: `Restore from USB`
  = `Восстановление с USB`
- `pick_backup`: `Pick a backup on the left.`
  = `Выберите копию слева.`
- `partitions_to_write`: `Partitions to write back:`
  = `Разделы для записи:`
- `greyed_out`: `Greyed out: recovery's own slot and the boot area (command line only).`
  = `Серым: свой слот восстановления и загрузочная область (только из командной строки).`
- `restore_dry_run`: `Restore (dry run)`
  = `Восстановление (проба)`
- `restoring`: `Restoring`
  = `Восстановление копии`
- `restore_backup_q`: `Restore backup?`
  = `Восстановить копию?`
- `restore_q`: `Write backup %s over these partitions of the printer:\n%s`
  = `Записать копию %s поверх этих разделов принтера:\n%s`
- `restore_q2`: `%s will be overwritten. This can't be undone. Keep the printer powered until it is done.`
  = `%s будут перезаписаны. Это нельзя отменить. Не выключайте принтер до конца.`
- `no_backups`: `No backups on this stick (folders %s...).`
  = `На этом накопителе нет копий (папки %s...).`
- `insert_backup_usb`: `Insert the USB stick with the backup.`
  = `Вставьте USB-накопитель с копией.`

### Restore stock firmware

- `stock_dry_run`: `Stock restore (dry run)`
  = `Возврат прошивки (проба)`
- `restoring_stock`: `Restoring stock firmware`
  = `Возврат стоковой прошивки`
- `restore_stock_q`: `Restore stock firmware?`
  = `Вернуть стоковую прошивку?`
- `stock_q_text`: `Writes the saved stock Flashforge system into the main slot (B) and makes it the one that starts. Kiln OS in slot B is replaced.`
  = `Записывает сохранённую стоковую систему Flashforge в основной слот (B) и делает её системой для запуска. Kiln OS в слоте B будет заменена.`
- `stock_q_text2`: `Slot B will be overwritten with the stock firmware. Keep the printer powered until it is done.`
  = `Слот B будет перезаписан стоковой прошивкой. Не выключайте принтер до конца.`
- `stock_saved_note`: `A saved stock system was found in /data/ad5x/stock.`
  = `Сохранённая стоковая система найдена в /data/ad5x/stock.`
- `stock_none_note`: `No saved stock system in /data/ad5x/stock: it is made by ad5x-update --replace-stock when Kiln OS is installed.`
  = `В /data/ad5x/stock нет сохранённой стоковой системы: её создаёт ad5x-update --replace-stock при установке Kiln OS.`
- `restore_stock_firmware`: `Restore stock firmware`
  = `Вернуть стоковую прошивку`
- `stock_back_title`: `Back to Flashforge's firmware`
  = `Возврат к прошивке Flashforge`
- `stock_text`: `Writes the stock system saved on the printer when Kiln OS was installed back into the main slot (B), checks it, and points the boot flag at it. This recovery stays as it is.`
  = `Записывает стоковую систему, сохранённую на принтере при установке Kiln OS, обратно в основной слот (B), проверяет её и направляет на неё флаг загрузки. Система восстановления остаётся как есть.`
- `stock_backup_first`: `Back up first to keep this system. You'll be asked twice before anything is written.`
  = `Сначала сделайте резервную копию, чтобы сохранить эту систему. Перед записью вас спросят дважды.`

### Network / SSH

- `address`: `Address`
  = `Адрес`
- `name`: `Name`
  = `Имя`
- `upload`: `Upload`
  = `Загрузка`
- `recovery_row`: `Recovery`
  = `Версия`
- `update_upload_page`: `Update upload page`
  = `Страница загрузки обновления`
- `plug_in`: `Plug in Ethernet, or set up Wi-Fi in /data/ad5x/wpa_supplicant.conf`
  = `Подключите Ethernet или настройте Wi-Fi в /data/ad5x/wpa_supplicant.conf`
- `ssh_login_text`: `Log in as root with the printer's root password or a key in /data/ad5x/ssh/authorized_keys. Network: /data/ad5x/network.conf.`
  = `Вход: root с паролем root принтера или ключом из /data/ad5x/ssh/authorized_keys. Сеть: /data/ad5x/network.conf.`

### Update count and boot markers

- `usb_summary`: `%sUSB %s (%s): %d %s`
  = `%sUSB %s (%s): %d %s`
- `update_one`: `update`
  = `обновление`
- `update_many`: `updates`
  = `обновл.`
- `flag_rescue_system`: `, rescue system`
  = `, аварийная система`
- `flag_rescue_boot`: `, rescue-boot marker`
  = `, метка rescue-boot`
- `flag_rescue_flash`: `, rescue-flash marker`
  = `, метка rescue-flash`
- `flag_autoupdate`: `, autoupdate marker`
  = `, метка autoupdate`

### Logs

- `empty_log`: `(empty)`
  = `(пусто)`
- `reading`: `reading…`
  = `чтение…`
- `logs_tab_session`: `This session`
  = `Этот сеанс`
- `logs_tab_updates`: `Updates`
  = `Обновления`
- `logs_tab_swupdate`: `SWUpdate`
  = `SWUpdate`
- `logs_tab_system`: `System`
  = `Система`

### Reboot / Power

- `rebooting`: `Rebooting`
  = `Перезагрузка`
- `shutting_down`: `Shutting down`
  = `Выключение`
- `reboot_main`: `the main OS (the boot flag says slot B)`
  = `основную ОС (флаг загрузки: слот B)`
- `reboot_recovery`: `recovery again (the boot flag says recovery)`
  = `восстановление снова (флаг загрузки: восстановление)`
- `reboot_text`: `The printer restarts into %s.`
  = `Принтер перезапустится в %s.`
- `reboot_q`: `Reboot?`
  = `Перезагрузить?`
- `shutdown_q`: `Shut down?`
  = `Выключить?`
- `shutdown_text`: `Stops the system so the printer can be switched off safely with its power switch.`
  = `Останавливает систему, чтобы принтер можно было безопасно выключить выключателем питания.`
- `power_text`: `"Shut down" stops the system so the printer can then be switched off with its power switch. Don't switch off during an install or restore: the partition being written would be left unusable.`
  = `«Выключить» останавливает систему, после чего принтер можно выключить выключателем питания. Не выключайте во время установки или восстановления: записываемый раздел станет непригодным.`
- `power_text2`: `"Boot main OS" sets the boot flag to the main OS (slot B) and restarts; "Reboot" keeps the flag as it is.`
  = `«Запустить ОС» ставит флаг загрузки на основную ОС (слот B) и перезапускает; «Перезагрузить» оставляет флаг как есть.`
- `reboot_into_flag`: `The printer restarts into the system the boot flag points at.`
  = `Принтер перезапустится в систему, на которую указывает флаг загрузки.`

### Progress and SWUpdate status

- `waiting_status`: `Waiting for a status query to finish…`
  = `Ожидание ответа на запрос состояния…`
- `receiving`: `Receiving the update: %u%%`
  = `Получение обновления: %u%%`
- `step_fmt`: `Step %u of %u: %s%s%s%s`
  = `Шаг %u из %u: %s%s%s%s`
- `preparing`: `preparing`
  = `подготовка`
- `swu_status`: `SWUpdate: %s`
  = `SWUpdate: %s`
- `swu_idle`: `idle`
  = `ожидание`
- `swu_starting`: `starting`
  = `запуск`
- `swu_installing`: `installing`
  = `установка`
- `swu_success`: `success`
  = `успешно`
- `swu_failed`: `failed`
  = `ошибка`
- `swu_receiving`: `receiving`
  = `получение`
- `swu_done`: `done`
  = `готово`
- `swu_subprocess`: `subprocess`
  = `подпроцесс`
- `swu_progress`: `progress`
  = `выполнение`
- `restarting`: `Restarting…`
  = `Перезапуск…`
- `working`: `Working…`
  = `Выполнение…`
- `working_dont_off`: `Working… don't switch off`
  = `Выполнение… не выключайте`
- `could_not_start`: `Could not start the command`
  = `Не удалось запустить команду`
- `job_done`: `%s: done`
  = `%s: готово`
- `job_stopped`: `%s: stopped`
  = `%s: остановлено`
- `update_failed`: `Update failed (see log)`
  = `Ошибка обновления (см. журнал)`
- `job_failed`: `%s: failed (exit %d)`
  = `%s: ошибка (код %d)`

### Sizes and the tools' progress lines (new, unchecked)

Sizes on the update, USB and restore pages now use these units (the number keeps its dot, as on the touch screen's
About page). The `pg_` lines are what Return to Flashforge firmware and the boot loader install show under the
progress bar while they run; the log below the bar stays English. `p1`/`p3`/`p4`, `kernel`, `kernel2`, `rootfs2`, `ota`,
`SPL` and `U-Boot` are partition and program names and stay as they are.

- `size_gb`: `%.1f GB`
  = `%.1f ГБ`
- `size_mb`: `%.0f MB`
  = `%.0f МБ`
- `size_kb`: `%.0f KB`
  = `%.0f КБ`
- `size_b`: `%llu B`
  = `%llu Б`
- `pg_checking`: `Checking`
  = `Проверка`
- `pg_done`: `Done`
  = `Готово`
- `pg_bl_spl`: `Writing Kiln's SPL`
  = `Запись SPL Kiln`
- `pg_bl_kernel2`: `Writing Kiln's 6.6 into kernel2`
  = `Запись ядра Kiln 6.6 в kernel2`
- `pg_bl_kernel`: `Writing Kiln's 6.6 into kernel`
  = `Запись ядра Kiln 6.6 в kernel`
- `pg_bl_uboot`: `Writing Kiln's U-Boot`
  = `Запись U-Boot Kiln`
- `pg_bl_step0`: `Step 0: the stock first MiB saved (/data, usershare)`
  = `Шаг 0: сохранение первого МБ eMMC со стоковым загрузчиком (/data, usershare)`
- `pg_bl_step1`: `Step 1: Kiln's SPL (0x4600-0xA3FF, the length at 0x4, the header sector last)`
  = `Шаг 1: запись SPL Kiln (0x4600-0xA3FF, длина по адресу 0x4, сектор заголовка последним)`
- `pg_bl_step1_up`: `Step 1: this build's SPL (0x4600-0xA3FF, the length at 0x4, the header sector last)`
  = `Шаг 1: запись SPL этой сборки (0x4600-0xA3FF, длина по адресу 0x4, сектор заголовка последним)`
- `pg_bl_step2`: `Step 2: kernel2 (p3) <- Kiln's 6.6`
  = `Шаг 2: запись ядра Kiln 6.6 в kernel2 (p3)`
- `pg_bl_step3`: `Step 3: kernel (p1) <- Kiln's 6.6`
  = `Шаг 3: запись ядра Kiln 6.6 в kernel (p1)`
- `pg_bl_step4`: `Step 4: U-Boot's settings, state and records in ota cleared`
  = `Шаг 4: очистка настроек, состояния и записей U-Boot в ota`
- `pg_bl_step4_up`: `Step 4: U-Boot's settings, state and records in ota: kept (an upgrade)`
  = `Шаг 4: настройки, состояние и записи U-Boot в ota сохраняются (обновление)`
- `pg_bl_step5`: `Step 5: Kiln's U-Boot at 0xA400 (body, then header)`
  = `Шаг 5: запись U-Boot Kiln по адресу 0xA400 (сначала тело, затем заголовок)`
- `pg_bl_step5_up`: `Step 5: this build's U-Boot at 0xA400 (the old header zeroed, the body, then the header)`
  = `Шаг 5: запись U-Boot этой сборки по адресу 0xA400 (обнуление старого заголовка, тело, затем заголовок)`
- `pg_rs_unpack`: `Unpacking %s`
  = `Распаковка %s`
- `pg_rs_root`: `Writing Flashforge's root (slot B)`
  = `Запись корневой системы Flashforge (слот B)`
- `pg_rs_step1`: `Step 1: Kiln's U-Boot out of 0xA400`
  = `Шаг 1: удаление U-Boot Kiln с адреса 0xA400`
- `pg_rs_step2`: `Step 2: U-Boot's settings in ota cleared`
  = `Шаг 2: очистка настроек U-Boot в ota`
- `pg_rs_step3`: `Step 3: rootfs2 (p4) <- stock root`
  = `Шаг 3: запись корневой системы стоковой прошивки в rootfs2 (p4)`
- `pg_rs_step4`: `Step 4: kernel2 (p3) <- stock kernel`
  = `Шаг 4: запись ядра стоковой прошивки в kernel2 (p3)`
- `pg_rs_step5`: `Step 5: kernel (p1) <- stock kernel`
  = `Шаг 5: запись ядра стоковой прошивки в kernel (p1)`
- `pg_rs_step6`: `Step 6: Flashforge's boot loader (SPL)`
  = `Шаг 6: запись загрузчика Flashforge (SPL)`
- `pg_rs_step7`: `Step 7: stock's board update armed, install state set`
  = `Шаг 7: подготовка обновления плат стоковой прошивкой, запись состояния установки`
- `pg_rs_step8`: `Step 8: boot flag -> slot B`
  = `Шаг 8: установка флага загрузки на слот B`

### Return to Flashforge firmware: removing Kiln OS's settings and files (new 2026-11-20, unchecked)

The two boxes on the Return to Flashforge page, the confirmation and the result. "Print files" is `файлы для печати` here (HelixScreen's section is `Файлы Gcode`).

- `rs_wipe_box`: `Also remove Kiln OS's settings and files (%s)`
  = `Также удалить настройки и файлы Kiln OS (%s)`
- `rs_prints_box`: `…and the uploaded print files too (%d files, %s)`
  = `…и загруженные файлы для печати (файлов: %d, %s)`
- `rs_wipe_note`: `Deleted for good once Flashforge's firmware is back: printer settings (Z offset, mesh), network, plugins, SSH keys, logs. Kept: Flashforge's files, the return's log and, unless ticked, the print files. Kiln OS installed later starts fresh, with its setup wizard.`
  = `Удаляются навсегда, когда прошивка Flashforge уже возвращена: настройки принтера (смещение по Z, сетка стола), сеть, плагины, ключи SSH, журналы. Остаются: файлы Flashforge, журнал возврата и, если не отмечено, файлы для печати. Kiln OS, установленная позже, начнёт заново, с мастером настройки.`
- `rs_q_wipe`: `Then Kiln OS's settings and files are deleted (%s): printer settings, network, plugins, SSH keys, logs. The print files and Flashforge's files stay.`
  = `Затем удаляются настройки и файлы Kiln OS (%s): настройки принтера, сеть, плагины, ключи SSH, журналы. Файлы для печати и файлы Flashforge остаются.`
- `rs_q_wipe_prints`: `Then Kiln OS's settings and files are deleted (%s), and the uploaded print files too (%d files, %s). Flashforge's files stay.`
  = `Затем удаляются настройки и файлы Kiln OS (%s), а также загруженные файлы для печати (файлов: %d, %s). Файлы Flashforge остаются.`
- `rs_q2_wipe`: `Kiln OS in the main slot will be gone, and its settings and files (%s) deleted for good: this can't be undone. Don't switch the printer off until the screen says it is done.`
  = `Kiln OS в основном слоте будет удалена, а её настройки и файлы (%s) будут удалены навсегда: это нельзя отменить. Не выключайте принтер, пока на экране не появится сообщение о завершении.`
- `rs_q2_wipe_prints`: `Kiln OS in the main slot will be gone, and its settings and files and the print files (%s in all) deleted for good: this can't be undone. Don't switch the printer off until the screen says it is done.`
  = `Kiln OS в основном слоте будет удалена, а её настройки, файлы и файлы для печати (всего %s) будут удалены навсегда: это нельзя отменить. Не выключайте принтер, пока на экране не появится сообщение о завершении.`
- `rs_wiped`: `Kiln OS's settings and files were removed (%s). The print files were kept.`
  = `Настройки и файлы Kiln OS удалены (%s). Файлы для печати сохранены.`
- `rs_wiped_prints`: `Kiln OS's settings and files and the print files were removed (%s).`
  = `Настройки и файлы Kiln OS, а также файлы для печати удалены (%s).`
- `rs_wipe_failed`: `Some of Kiln OS's files couldn't be removed; Flashforge's firmware is back all the same. The log /data/ad5x/return-stock/log lists them.`
  = `Часть файлов Kiln OS удалить не удалось; прошивка Flashforge всё равно возвращена. Они перечислены в журнале /data/ad5x/return-stock/log.`
- `pg_rs_step9`: `Step 9: Kiln OS's settings and files removed`
  = `Шаг 9: удаление настроек и файлов Kiln OS`

### Return to Flashforge firmware (unchecked)

The page, its check and its two confirmations. `slot A` / `слот A` is the recovery's own slot. `rs_refused` is followed by one of the reasons in the next group.

- `rs_title`: `Return to Flashforge firmware`
  = `Вернуть прошивку Flashforge`
- `rs_text`: `Puts Flashforge's own firmware back into the main slot and starts it. Kiln OS in the main slot is removed. This recovery stays as a safety net.`
  = `Возвращает стоковую прошивку Flashforge в основной слот и запускает её. Kiln OS в основном слоте удаляется, система восстановления остаётся.`
- `rs_files`: `Flashforge files: %s`
  = `Источник: %s`
- `rs_src_stock`: `the stock copy saved on this printer (/data/ad5x/stock)`
  = `копия стоковой прошивки, сохранённая на принтере (/data/ad5x/stock)`
- `rs_src_usershare`: `the stock copy on the usershare partition`
  = `копия стоковой прошивки в разделе usershare`
- `rs_src_copy`: `the stock copy in %s`
  = `копия стоковой прошивки в %s`
- `rs_src_backup`: `the install stick's backup %s`
  = `резервная копия %s с установочного USB-накопителя`
- `rs_src_package`: `Flashforge's update package %s`
  = `пакет обновления Flashforge %s`
- `rs_after`: `After it: %s`
  = `После этого: %s`
- `rs_after_kiln`: `Flashforge's firmware in the main slot, started by Kiln's boot loader as Flashforge's would (its second stage, U-Boot, removed); this recovery stays in slot A`
  = `прошивка Flashforge в основном слоте, её запускает загрузчик Kiln (U-Boot из него удаляется). Система восстановления остаётся в слоте A`
- `rs_after_ffspl`: `Flashforge's firmware in the main slot, and Flashforge's own boot loader back; this recovery stays in slot A`
  = `прошивка Flashforge в основном слоте и снова стоковый загрузчик Flashforge. Система восстановления остаётся в слоте A`
- `rs_after_ff`: `Flashforge's firmware in the main slot (Flashforge's boot loader stays); this recovery stays in slot A`
  = `прошивка Flashforge в основном слоте (загрузчик Flashforge не меняется). Система восстановления остаётся в слоте A`
- `rs_config`: `Flashforge's printer.cfg: %s`
  = `printer.cfg стоковой прошивки: %s`
- `rs_cfg_zmod`: `Flashforge's printer.cfg: %d zMod include line(s) to switch off (zMod is gone; the old file is kept)`
  = `В printer.cfg стоковой прошивки будут отключены строки [include] от zMod: %d (zMod удалён; старый файл сохранится)`
- `rs_cfg_missing`: `Flashforge's printer.cfg: %d include line(s) to switch off (their files are missing; the old file is kept)`
  = `В printer.cfg стоковой прошивки будут отключены строки [include] на отсутствующие файлы: %d (старый файл сохранится)`
- `rs_cfg_mixed`: `Flashforge's printer.cfg: %d include line(s) to switch off (zMod's, or their files are missing; the old file is kept)`
  = `В printer.cfg стоковой прошивки будут отключены строки [include] от zMod или на отсутствующие файлы: %d (старый файл сохранится)`
- `rs_cfg_failed`: `Flashforge's printer.cfg couldn't be changed and was left as it was. The return went on, but Flashforge's Klipper may not start until the [include] lines for missing files (zMod's) are removed.`
  = `Не удалось изменить printer.cfg стоковой прошивки, он остался прежним. Возврат продолжен, но Klipper может не запуститься, пока из файла не удалены строки [include] от zMod.`
- `rs_checking`: `Looking for Flashforge's files…`
  = `Поиск файлов Flashforge…`
- `rs_ready`: `Ready. Nothing is written before you tap Return to Flashforge.`
  = `Готово. Ничего не записывается, пока вы не нажмёте «Вернуть Flashforge».`
- `rs_resume`: `A return was stopped before it finished (for example by a power cut). Tap Continue to finish it.`
  = `Возврат был прерван (например, при отключении питания). Нажмите «Продолжить», чтобы его завершить.`
- `rs_refused`: `Not possible now: %s`
  = `Сейчас невозможно: %s`
- `rs_done_already`: `Done. Switch the printer off and on: Flashforge's firmware starts.`
  = `Готово. Выключите и включите принтер: запустится прошивка Flashforge.`
- `rs_no_files`: `No Flashforge files found. Put Flashforge's update file (AD5X-….tgz, from Flashforge's website) on a USB stick, then tap Check.`
  = `Не найдены файлы Flashforge. Запишите файл обновления Flashforge (AD5X-….tgz с сайта Flashforge) на USB-флешку и нажмите «Проверить».`
- `rs_spl_box`: `Also put back Flashforge's own boot loader`
  = `Вернуть и стоковый загрузчик Flashforge`
- `rs_spl_missing`: `Flashforge's own boot loader can't be put back: this printer's saved copy of it (boot.img) wasn't found. Flashforge's firmware works all the same: Kiln's boot loader starts it.`
  = `Стоковый загрузчик Flashforge вернуть нельзя: сохранённая копия загрузчика этого принтера (boot.img) не найдена. Прошивка Flashforge всё равно будет работать: её запустит загрузчик Kiln.`
- `rs_go`: `Return to Flashforge`
  = `Вернуть Flashforge`
- `rs_continue`: `Continue`
  = `Продолжить`
- `rs_save_usb`: `Save files to USB`
  = `Сохранить на USB`
- `rs_q`: `Return to Flashforge firmware?`
  = `Вернуть прошивку Flashforge?`
- `rs_q_text`: `Writes Flashforge's system into the main slot and makes it the one that starts. Kiln OS in the main slot is removed. It takes a few minutes.`
  = `Записывает систему Flashforge в основной слот и делает её системой для запуска. Kiln OS в основном слоте удаляется. Это займёт несколько минут.`
- `rs_q_text2`: `Kiln OS in the main slot will be gone. Don't switch the printer off until the screen says it is done.`
  = `Kiln OS в основном слоте будет удалена. Не выключайте принтер, пока на экране не появится сообщение о завершении.`
- `rs_running`: `Returning to Flashforge firmware`
  = `Возврат прошивки Flashforge`
- `rs_checking_title`: `Checking for Flashforge's files`
  = `Поиск файлов Flashforge`
- `rs_saving`: `Saving Flashforge files to USB`
  = `Сохранение файлов Flashforge на USB`
- `rs_locked_q`: `Return to Flashforge not finished`
  = `Возврат прошивки Flashforge не завершён`
- `rs_locked_text`: `A Return to Flashforge firmware was started and not finished, so the main slot may hold only part of a system. Finish it first.`
  = `Возврат прошивки Flashforge был начат и не завершён, поэтому в основном слоте может быть только часть системы. Сначала завершите его.`
- `rs_open`: `Open`
  = `Открыть`

### Why something is not possible now (new 2026-11-21, unchecked)

The reason after `rs_refused` (`Сейчас невозможно: %s`) on the Return to Flashforge and boot loader pages. Until now the screen showed the tool's English text here; it now shows these lines, and `why_other` for any reason without a line of its own (the English details stay in Logs > This session). They start with a small letter because they follow the colon.

- `why_busy`: `another job is still running: wait for it to finish, then tap Check`
  = `ещё выполняется другая задача: дождитесь её завершения и нажмите «Проверить»`
- `why_rs_unfinished`: `a Return to Flashforge firmware was started and not finished: finish it first`
  = `возврат прошивки Flashforge был начат и не завершён: сначала завершите его`
- `why_no_stock`: `no Flashforge files found`
  = `не найдены файлы Flashforge`
- `why_board`: `this printer's board is not on the list of known boards`
  = `платы этого принтера нет в списке известных плат`
- `why_chip`: `Kiln's boot loader is not known to work on this printer's chip`
  = `неизвестно, работает ли загрузчик Kiln на чипе этого принтера`
- `why_no_main`: `slot B holds no working Kiln OS: install Kiln OS first`
  = `в слоте B нет рабочей Kiln OS: сначала установите Kiln OS`
- `why_update_main`: `the Kiln OS in slot B is too old for this: update Kiln OS first`
  = `Kiln OS в слоте B слишком старая для этого: сначала обновите Kiln OS`
- `why_recovery_old`: `this recovery is not the one the Kiln OS in slot B brings: start Kiln OS once (it brings this recovery up to date), then try again`
  = `эта система восстановления не та, что поставляется с Kiln OS в слоте B: запустите Kiln OS один раз (она обновит систему восстановления) и повторите`
- `why_k66_failed`: `Kiln OS recorded its 6.6 kernel as failed: start Kiln OS on 6.6 first (ad5x-kernel retry)`
  = `Kiln OS отметила ядро 6.6 как неудачное: сначала запустите Kiln OS на ядре 6.6 (ad5x-kernel retry)`
- `why_data_full`: `less than 2 MB free on the data partition (/data)`
  = `в разделе данных (/data) свободно меньше 2 МБ`
- `why_no_upgrade`: `there is no Kiln boot loader of another release here to update`
  = `здесь нет загрузчика Kiln из другого выпуска, который можно обновить`
- `why_ffspl`: `no saved copy of this printer's Flashforge boot loader (boot.img), so it can't be put back`
  = `нет сохранённой копии загрузчика Flashforge этого принтера (boot.img), поэтому его нельзя вернуть`
- `why_wipe`: `Kiln OS's settings and files can't be removed safely now`
  = `настройки и файлы Kiln OS сейчас нельзя безопасно удалить`
- `why_other`: `a safety check failed (details: Logs > This session)`
  = `не пройдена одна из проверок безопасности (подробности: Журналы > Этот сеанс)`

### Kiln's boot loader (unchecked)

The install and update of Kiln's own boot loader. `J28` is the board's USB connector; `SPL`, `U-Boot`, `6.6` and `7.3` stay as they are.

- `bl_entry`: `Install Kiln's boot loader…`
  = `Установить загрузчик Kiln…`
- `bl_title`: `Kiln's boot loader`
  = `Загрузчик Kiln`
- `bl_text`: `Replaces Flashforge's boot loader with Kiln's own (SPL and U-Boot): no Flashforge code starts the printer any more, and a Kiln OS kernel that fails to start falls back by itself (7.3, then 6.6, then this recovery). Proven on one printer so far (one more board is known to match). If the printer doesn't start after it, the only proven way back needs the printer opened (its J28 USB connector). Return to Flashforge firmware puts Flashforge's boot loader back.`
  = `Ставит загрузчик Kiln (SPL и U-Boot) вместо Flashforge: код Flashforge больше не запускает принтер, а если ядро Kiln OS не запустится, загрузка сама откатывается (7.3, затем 6.6, затем восстановление). Пока проверено на одном принтере (известна ещё одна такая же плата). Если затем принтер не запустится, проверенный способ вернуть его один: вскрыть принтер (USB-порт J28). «Вернуть прошивку Flashforge» вернёт загрузчик Flashforge.`
- `bl_board_known`: `This printer's board: on the list of known boards.`
  = `Плата этого принтера: есть в списке известных плат.`
- `bl_board_unknown`: `This printer's board is not on the list of known boards, so it isn't offered here. To help get it added, see the boot loader guide: "Is my printer one of the known boards?"`
  = `Платы этого принтера нет в списке известных, поэтому установка не предлагается. Как помочь её добавить, сказано в руководстве по загрузчику, раздел «Is my printer one of the known boards?».`
- `bl_checking`: `Checking…`
  = `Проверка…`
- `bl_ready`: `Ready. Nothing is written before you tap Install and confirm twice.`
  = `Готово. Ничего не записывается, пока вы не нажмёте «Установить» и не подтвердите дважды.`
- `bl_resume`: `An install was stopped before it finished (for example by a power cut). Tap Continue to finish it.`
  = `Установка была прервана (например, при отключении питания). Нажмите «Продолжить», чтобы её завершить.`
- `bl_installed`: `Installed. Restart the printer: Kiln's boot loader then starts this recovery screen, which shows the result.`
  = `Установлено. Перезапустите принтер: загрузчик Kiln запустит этот экран восстановления, где будет виден результат.`
- `bl_verified`: `Done: Kiln's boot loader is installed and started this recovery. Boot main OS starts Kiln OS through it.`
  = `Готово: загрузчик Kiln установлен и запустил это восстановление. «Запустить ОС» загружает Kiln OS через него.`
- `bl_unverified`: `Installed, but this start didn't come through Kiln's U-Boot (Kiln's SPL started the system itself). The printer works: Boot main OS starts Kiln OS. Please post this, with what Check shows, in issue #68 (github.com/djvalic/kiln-os).`
  = `Установлено, но этот запуск прошёл без U-Boot Kiln (систему запустил сам SPL Kiln). Принтер работает: «Запустить ОС» загружает Kiln OS. Пожалуйста, сообщите об этом в теме #68 на GitHub (github.com/djvalic/kiln-os) и приложите то, что показывает «Проверить».`
- `bl_wait_auto`: `Waiting for the start-up actions to finish, then checking…`
  = `Ожидание завершения автоматических действий при запуске, затем проверка…`
- `bl_up_to_date`: `Kiln's boot loader is installed and up to date: nothing to install.`
  = `Загрузчик Kiln установлен и актуален: устанавливать нечего.`
- `bl_go`: `Install`
  = `Установить`
- `bl_q`: `Install Kiln's boot loader?`
  = `Установить загрузчик Kiln?`
- `bl_q_text`: `Writes Kiln's SPL and U-Boot into the boot area of the printer's memory, and Kiln's 6.6 kernel into both kernel slots. It takes under a minute. Proven on one printer so far.`
  = `Записывает SPL и U-Boot Kiln в загрузочную область памяти принтера, а ядро Kiln 6.6 — в оба слота ядра. Это займёт меньше минуты. Пока проверено на одном принтере.`
- `bl_q_text2`: `If the printer doesn't start afterwards, bringing it back needs the printer opened and a USB cable (J28). Don't switch the printer off until the screen says it is done.`
  = `Если после этого принтер не запустится, для возврата к работе нужно вскрыть принтер и подключить USB-кабель (J28). Не выключайте принтер, пока на экране не появится сообщение о завершении.`
- `bl_running`: `Installing Kiln's boot loader`
  = `Установка загрузчика Kiln`
- `bl_checking_title`: `Checking Kiln's boot loader`
  = `Проверка загрузчика Kiln`
- `bl_up_entry`: `Update Kiln's boot loader…`
  = `Обновить загрузчик Kiln…`
- `bl_up_title`: `Update Kiln's boot loader`
  = `Обновление загрузчика Kiln`
- `bl_up_text`: `This printer already starts through Kiln's own boot loader (SPL and U-Boot), but one from another Kiln OS release. This replaces it with the boot loader this release carries, and its fixes. Your settings and files stay as they are. If the printer doesn't start after it, the only proven way back needs the printer opened (its J28 USB connector).`
  = `Принтер уже запускается через загрузчик Kiln (SPL и U-Boot), но из другого выпуска Kiln OS. Обновление заменит его загрузчиком этого выпуска, с его исправлениями. Настройки и файлы не меняются. Если затем принтер не запустится, проверенный способ вернуть его один: вскрыть принтер (USB-порт J28).`
- `bl_up_builds`: `Now: %s. After the update: %s`
  = `Сейчас: %s. После обновления: %s`
- `bl_up_ready`: `Ready. Nothing is written before you tap Update and confirm twice.`
  = `Готово. Ничего не записывается, пока вы не нажмёте «Обновить» и не подтвердите дважды.`
- `bl_up_resume`: `An update was stopped before it finished (for example by a power cut). Tap Continue to finish it.`
  = `Обновление было прервано (например, при отключении питания). Нажмите «Продолжить», чтобы его завершить.`
- `bl_up_done`: `Updated. Restart the printer: Kiln's boot loader then starts this recovery screen, which shows the result.`
  = `Обновлено. Перезапустите принтер: загрузчик Kiln запустит этот экран восстановления, где будет виден результат.`
- `bl_up_verified`: `Done: Kiln's boot loader is updated and started this recovery. Boot main OS starts Kiln OS through it.`
  = `Готово: загрузчик Kiln обновлён и запустил это восстановление. «Запустить ОС» загружает Kiln OS через него.`
- `bl_up_unverified`: `Updated, but this start didn't come through Kiln's U-Boot (Kiln's SPL started the system itself). The printer works: Boot main OS starts Kiln OS. Please post this, with what Check shows, in issue #68 (github.com/djvalic/kiln-os).`
  = `Обновлено, но этот запуск прошёл без U-Boot Kiln (систему запустил сам SPL Kiln). Принтер работает: «Запустить ОС» загружает Kiln OS. Пожалуйста, сообщите об этом в теме #68 на GitHub (github.com/djvalic/kiln-os) и приложите то, что показывает «Проверить».`
- `bl_up_go`: `Update`
  = `Обновить`
- `bl_up_q`: `Update Kiln's boot loader?`
  = `Обновить загрузчик Kiln?`
- `bl_up_q_text`: `Writes this release's Kiln SPL and U-Boot over the older ones in the boot area of the printer's memory; a copy of the older ones is kept first. It takes under a minute.`
  = `Записывает SPL и U-Boot Kiln из этого выпуска поверх прежних в загрузочную область памяти принтера; копия прежних сохраняется заранее. Это займёт меньше минуты.`
- `bl_up_running`: `Updating Kiln's boot loader`
  = `Обновление загрузчика Kiln`

### Kiln's boot loader line on Reboot / Power (new 2026-11-22, unchecked)

One line of 16 px above the buttons, always there (issue #97). `%s` is a build date ("Nov 19 2026 - 08:31:00"); the line should stay on one line where a button is below it (`bl_line_update`), so keep it short.

- `bl_line_reading`: `Kiln's boot loader: reading…`
  = `Загрузчик Kiln: чтение…`
- `bl_line_unknown`: `Kiln's boot loader: state unknown (couldn't be read)`
  = `Загрузчик Kiln: состояние неизвестно (не удалось прочитать)`
- `bl_line_current`: `Kiln's boot loader: installed, build %s, up to date`
  = `Загрузчик Kiln: установлен, сборка %s, актуален`
- `bl_line_update`: `Kiln's boot loader: installed, build %s, update available`
  = `Загрузчик Kiln: установлен, сборка %s, есть обновление`
- `bl_line_other`: `Kiln's boot loader: installed, build %s (this recovery carries build %s)`
  = `Загрузчик Kiln: установлен, сборка %s (в этой системе восстановления сборка %s)`
- `bl_line_older`: `Kiln's boot loader: installed, build %s (this recovery carries an older build, %s)`
  = `Загрузчик Kiln: установлен, сборка %s (в этой системе восстановления более старая сборка, %s)`
- `bl_line_installed`: `Kiln's boot loader: installed, build %s`
  = `Загрузчик Kiln: установлен, сборка %s`
- `bl_line_spl`: `Kiln's boot loader: only Kiln's SPL is there, no U-Boot`
  = `Загрузчик Kiln: есть только SPL Kiln, без U-Boot`
- `bl_line_flashforge`: `Kiln's boot loader: not installed, Flashforge's boot loader starts the printer`
  = `Загрузчик Kiln: не установлен, принтер запускает загрузчик Flashforge`

### Automatic update at start (unchecked)

The full-screen page while an update from the update folder or a USB stick installs at start.

- `auto_title`: `Installing Kiln OS`
  = `Установка Kiln OS`
- `auto_step_fmt`: `Step %u of %u: %s`
  = `Шаг %u из %u: %s`
- `auto_step_check`: `Unpacking and checking the update`
  = `Распаковка и проверка обновления`
- `auto_step_write`: `Writing Kiln OS`
  = `Запись Kiln OS`
- `auto_step_restart`: `Restarting into Kiln OS`
  = `Перезапуск в Kiln OS`
- `auto_dont_off`: `Don't switch the printer off`
  = `Не выключайте принтер`
- `auto_dont_off_text`: `This takes a few minutes. The printer restarts by itself when it is done.`
  = `Это займёт несколько минут. Когда всё будет готово, принтер перезапустится сам.`
- `auto_restart_text`: `Kiln OS starts next. Its first start takes a few minutes more.`
  = `Сейчас запустится Kiln OS. Первый запуск займёт ещё несколько минут.`
- `auto_failed`: `Kiln OS was not installed`
  = `Kiln OS не установлена`
- `auto_failed_text`: `The update failed. The printer stays in the recovery OS. Logs > Updates says why.`
  = `Обновление не удалось. Принтер остаётся в системе восстановления. Причина указана в разделе Журналы > Обновления.`

### Last update on the home screen (new 2026-11-21, unchecked)

The text after `home_last_update` (`Последнее обновление: %s`). The first `%s` is the date and time (`2026-10-15 21:04`), the second the update's file name. Until now the screen showed the English line of the update log here. The line is cut at the right edge, so the time and the outcome come first.

- `upd_ok`: `%s, installed in slot B: %s`
  = `%s — установлено в слот B: %s`
- `upd_ok_nofile`: `%s, installed in slot B`
  = `%s — установлено в слот B`
- `upd_failed`: `%s, failed: %s`
  = `%s, ошибка установки: %s`
- `upd_failed_nofile`: `%s, failed`
  = `%s, ошибка установки`
- `upd_started`: `%s, started, not finished: %s`
  = `%s, начато, но не завершено: %s`
- `upd_skipped`: `%s, installed before, skipped: %s`
  = `%s, уже устанавливалось, пропущено: %s`
- `upd_other`: `%s, see Logs > Updates`
  = `%s, см. Журналы > Обновления`

### Two short words (unchecked)

`swu_staged` marks an update file already in the update folder; `n_partitions` is the count on the Restore page.

- `swu_staged`: `staged`
  = `на принтере`
- `n_partitions`: `%d partitions`
  = `разделов: %d`

## 7. New in HelixScreen v1.1.0-rc.1 and beta.18

HelixScreen keys that are new since the beta.17 list. HelixScreen ships Russian for all of them, so they do not
show in English, but nobody here has checked that Russian yet. Some of them only show on other printers; that is
noted per group.

### v1.1.0-rc.1

41 keys came with rc.1.

<details><summary>What's new tour (10)</summary>

Shows once, on the first start after the update; Help & About replays it.

- `New in 1.1`
  = `Новое в 1.1`
- `Here's a quick look at what changed since your last version.`
  = `Краткий обзор изменений с вашей последней версии.`
- `Long-press any tile to enter edit mode. The rebuilt grid lets you rearrange, resize, remove, or add widgets, and drag them between pages.`
  = `Удерживайте плитку, чтобы войти в режим редактирования. Новая сетка позволяет переставлять, менять размер, удалять и добавлять виджеты, а также перетаскивать их между страницами.`
- `A new Print Status screen`
  = `Новый экран статуса печати`
- `During a print, see a chip for each heater, fan, and light, a checklist of the start sequence, and progress with controls in one strip.`
  = `Во время печати вы видите индикатор каждого нагревателя, вентилятора и подсветки, список шагов запуска, а также прогресс и управление в одной полосе.`
- `Load, unload, and swap spools, set temperatures, and monitor runout sensors.`
  = `Загружайте, выгружайте и меняйте катушки, задавайте температуру и следите за датчиками филамента.`
- `Load and unload`
  = `Загрузка и выгрузка`
- `Load, unload, and purge from here. Choose a material to set its temperatures first.`
  = `Здесь можно загрузить, выгрузить и продуть филамент. Сначала выберите материал, чтобы задать его температуру.`
- `Your filament system`
  = `Ваша система филамента`
- `Tap a slot to load or unload it, pick a spool, or edit its details. Your edits stay in step with the printer and Spoolman.`
  = `Нажмите на слот, чтобы загрузить или выгрузить его, выбрать катушку или изменить данные. Ваши правки остаются согласованными с принтером и Spoolman.`

</details>

<details><summary>Setup Timelapse (10)</summary>

- `Checking for ffmpeg...`
  = `Поиск ffmpeg...`
- `Downloading the timelapse plugin...`
  = `Загрузка плагина таймлапса...`
- `Installing the timelapse plugin...`
  = `Установка плагина таймлапса...`
- `Adding the timelapse plugin to Moonraker...`
  = `Добавление плагина таймлапса в Moonraker...`
- `An earlier install is still finishing...`
  = `Предыдущая установка ещё завершается...`
- `Could not download the timelapse plugin. Check the printer's internet connection.`
  = `Не удалось скачать плагин таймлапса. Проверьте подключение принтера к интернету.`
- `Could not add the timelapse plugin to Moonraker.`
  = `Не удалось добавить плагин таймлапса в Moonraker.`
- `Installing restarts Moonraker, so it waits until the print is finished or cancelled.`
  = `Установка перезапускает Moonraker, поэтому ждёт, пока печать не завершится или не будет отменена.`
- `The timelapse plugin is installed. Making videos also needs ffmpeg, which is not installed on this printer.`
  = `Плагин таймлапса установлен. Для создания видео также нужен ffmpeg, который не установлен на этом принтере.`
- `To make videos, run this on your printer via SSH:`
  = `Чтобы создавать видео, выполните это на принтере через SSH:`

</details>

<details><summary>Advanced > HelixPrint Plugin (18)</summary>

The feature list and the reasons a feature can't run, including power loss recovery.

- `RUNNING`
  = `РАБОТАЕТ`
- `NOT AVAILABLE HERE`
  = `ЗДЕСЬ НЕДОСТУПНО`
- `The plugin didn't say why.`
  = `Плагин не указал причину.`
- `Failed to start. See the Moonraker log.`
  = `Не удалось запустить. См. журнал Moonraker.`
- `Stopped. Restart Moonraker to start it again.`
  = `Остановлено. Перезапустите Moonraker, чтобы запустить снова.`
- `Needs file analysis, which isn't running.`
  = `Нужен анализ файлов, который не запущен.`
- `Needs a newer Moonraker to hold uploads.`
  = `Нужен более новый Moonraker, чтобы задерживать загрузки.`
- `Timelapse or logs folder overlaps a protected one.`
  = `Папка таймлапсов или журналов пересекается с защищённой.`
- `A folder name in moonraker.conf is unsafe.`
  = `Имя папки в moonraker.conf небезопасно.`
- `Not set up for this printer model yet.`
  = `Для этой модели принтера пока не настроено.`
- `Waiting to read the printer's configuration from Klipper.`
  = `Ожидание чтения конфигурации принтера из Klipper.`
- `A delta printer can't home X and Y without moving Z, so a print can't be resumed.`
  = `Дельта-принтер не может выполнить парковку X и Y без движения Z, поэтому печать нельзя продолжить.`
- `This printer's gantry drops when the power is cut, so a print can't be resumed.`
  = `Портал этого принтера опускается при отключении питания, поэтому печать нельзя продолжить.`
- `This printer's homing override homes Z along with X and Y, so a print can't be resumed.`
  = `Homing override этого принтера паркует Z вместе с X и Y, поэтому печать нельзя продолжить.`
- `This printer's homing override sets the Z position when it homes X and Y, so a print can't be resumed.`
  = `Homing override этого принтера задаёт положение Z при парковке X и Y, поэтому печать нельзя продолжить.`
- `This printer's homing override runs commands that may move Z, so a print can't be resumed.`
  = `Homing override этого принтера выполняет команды, которые могут сдвинуть Z, поэтому печать нельзя продолжить.`
- `This printer's firmware has its own power-loss recovery.`
  = `Прошивка этого принтера имеет собственное восстановление после отключения питания.`
- `Reboot the printer to finish the plugin update.`
  = `Перезагрузите принтер, чтобы завершить обновление плагина.`

</details>

<details><summary>Spool editor (filament slot) (3)</summary>

- `Unlink`
  = `Отвязать`
- `Re-apply spool`
  = `Применить катушку снова`
- `The linked spool says {}.`
  = `Привязанная катушка указывает: {}.`

</details>

### v1.1.0-beta.18

41 keys came with beta.18. `Select a valid number ({}-{})` replaces `Select a valid number (1-{})`.

<details><summary>Print start (2)</summary>

- `Heating chamber`
  = `Нагрев камеры`
- `Waiting for bed temperature...`
  = `Ожидание температуры стола...`

</details>

<details><summary>Connecting to the printer (setup wizard) (1)</summary>

- `Connected to Moonraker, but Klipper reported an error. You can continue, and HelixScreen will show it again after setup. Hardware detection stays limited until Klipper starts.`
  = `Подключено к Moonraker, но Klipper сообщил об ошибке. Можно продолжить, HelixScreen покажет её снова после настройки. Обнаружение оборудования ограничено, пока Klipper не запустится.`

</details>

<details><summary>Klipper configuration error and Moonraker restart (5)</summary>

- `Klipper Config Error`
  = `Ошибка конфигурации Klipper`
- `Klipper could not load its configuration. Fix the setting below in the printer's config files, then restart Klipper.`
  = `Klipper не смог загрузить конфигурацию. Исправьте указанный ниже параметр в файлах конфигурации принтера, затем перезапустите Klipper.`
- `Restart Moonraker?`
  = `Перезапустить Moonraker?`
- `The screen will lose its connection to the printer for a few seconds.`
  = `Экран потеряет связь с принтером на несколько секунд.`
- `Cannot restart Moonraker while printing`
  = `Нельзя перезапустить Moonraker во время печати`

</details>

<details><summary>Z offset (8)</summary>

The tool and head lines only show on printers with several toolheads, not on the AD5X.

- `Saved {} mm`
  = `Сохранено {} мм`
- `Saved {} mm, {} mm after Save`
  = `Сохранено {} мм, {} мм после сохранения`
- `This printer has no {} command, so the Z-offset cannot be saved.`
  = `У этого принтера нет команды {}, поэтому Z-смещение нельзя сохранить.`
- `Calibrate with this tool?`
  = `Калибровать с этим инструментом?`
- `No tool is known to be mounted. With one shared probe, calibrate with {}. Continue anyway?`
  = `Неизвестно, какой инструмент установлен. С общим датчиком калибруйте с {}. Всё равно продолжить?`
- `{0} is mounted. With one shared probe, calibrate with {1}. Continue with {0}?`
  = `Установлен {0}. С общим датчиком калибруйте с {1}. Продолжить с {0}?`
- `Each head keeps its own Z offset on this printer. Use its tool offset calibration instead.`
  = `У каждой печатающей головки на этом принтере своё Z-смещение. Используйте калибровку смещений инструментов.`
- `Saved for the mounted head; other heads keep their own`
  = `Сохранено для установленной печатающей головки; остальные головки сохраняют своё`

</details>

<details><summary>Filament system (IFS slots) and Settings > Printing (9)</summary>

- `Clear Error`
  = `Сбросить ошибку`
- `Loading lane details…`
  = `Загрузка сведений о канале…`
- `Loading lane details. Try again in a moment.`
  = `Загрузка сведений о канале. Повторите попытку через минуту.`
- `Not saved: {}. Try again.`
  = `Не сохранено: {}. Попробуйте ещё раз.`
- `the printer did not confirm it`
  = `принтер не подтвердил`
- `the printer refused it`
  = `принтер отклонил`
- `Select a valid number ({}-{})`
  = `Выберите корректный номер ({}-{})`
- `Number slots from 0`
  = `Нумеровать слоты с 0`
- `Show slots, lanes, gates and tools counting from 0, matching T0 in G-code`
  = `Считать слоты, каналы, шлюзы и инструменты с 0, как T0 в G-коде`

</details>

<details><summary>Other filament units (10)</summary>

Shown only with these units, never on the AD5X with its IFS.

- `Change the name or the linked spool in Spoolman.`
  = `Меняйте название или привязанную катушку в Spoolman.`
- `OpenAMS keeps this spool in Spoolman, which takes only material, color, brand and weight here`
  = `OpenAMS хранит эту катушку в Spoolman, который здесь принимает только материал, цвет, бренд и вес`
- `OpenAMS manages this spool's link`
  = `Привязкой этой катушки управляет OpenAMS`
- `AFC has no Spoolman configured`
  = `В AFC не настроен Spoolman`
- `Make color, material and spool changes in Spoolman.`
  = `Меняйте цвет, материал и катушку в Spoolman.`
- `this printer fills its gates from Spoolman, so change the spool there`
  = `этот принтер берёт гейты из Spoolman, меняйте катушку там`
- `the ACE needs a material and its nozzle temperature`
  = `ACE нужен материал и его температура сопла`
- `the CFS can't change a slot while a print is running`
  = `CFS не может изменить слот во время печати`
- `the QIDI Box filament list has not loaded`
  = `список филаментов QIDI Box не загружен`
- `the QIDI Box has no {} in its filament list`
  = `в списке филаментов QIDI Box нет {}`

</details>

<details><summary>Printing a .3mf file (4)</summary>

- `The queue prints this .3mf's default plate. Print this plate from here instead.`
  = `Очередь печатает стандартную пластину этого .3mf. Напечатайте эту пластину отсюда.`
- `The pre-print steps you turned off cannot be applied to this .3mf. Turn them back on to print it.`
  = `Отключённые шаги подготовки нельзя применить к этому .3mf. Включите их снова, чтобы напечатать.`
- `Filament Mapping cannot rewrite this .3mf. Print it without remapping.`
  = `Сопоставление филамента не может переписать этот .3mf. Напечатайте его без переназначения.`
- `This .3mf's plates are still loading. Try again in a moment.`
  = `Пластины этого .3mf ещё загружаются. Попробуйте снова через мгновение.`

</details>

<details><summary>Label printers (network) (2)</summary>

- `The printer requires an encrypted connection, but it rejected the encrypted job: HTTP {} {}`
  = `Принтер требует зашифрованного соединения, но отклонил зашифрованное задание: HTTP {} {}`
- `The printer requires an encrypted connection, but the encrypted connection to {}:{} failed`
  = `Принтер требует зашифрованного соединения, но зашифрованное подключение к {}:{} не удалось`

</details>
