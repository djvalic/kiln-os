# Russian translation: what is missing or untranslated

Kiln OS's touch screen is HelixScreen v1.1.0-rc.1 with Kiln's patches. This list was made on 2026-11-11 from
[helixscreen-ru.yml](helixscreen-ru.yml) and [helixscreen-en.yml](helixscreen-en.yml) in this folder, and from
the recovery screen's [en.txt](../../recovery-ui/i18n/en.txt) and [ru.txt](../../recovery-ui/i18n/ru.txt).

## Summary

- `helixscreen-en.yml` has 4901 keys. `helixscreen-ru.yml` has the same 4901 keys: none is missing.
- 111 Russian values are the same as the English text. They are names, units and numbers that stay as they are, and `Pressure Advance`, which stays English on purpose (section 4).
- 7 more values have no Cyrillic but differ from English on purpose (for example `AMS` reads `IFS`, `WiFi` reads `Wi-Fi`).
- 243 keys belong to Kiln OS's own screens. I wrote their Russian myself, so they need a native speaker's check most (section 5). 14 of them are new since the last list: Boot into recovery, Log detail, the two Auto-Refill rows of the IFS settings, and SELECTOR and HUB on the IFS drawing.
- 41 keys are new in HelixScreen v1.1.0-rc.1, and the 41 that came with v1.1.0-beta.18 are still unchecked. HelixScreen ships Russian for all of them, so nothing shows in English, but nobody here has checked that Russian yet (section 7). rc.1 also removed 9 older keys whose texts it rewrote (the HelixPrint plugin reasons and the tour).
- A few open questions and texts that are still English on the screen (section 1).
- Recovery screen: all 155 lines of `ru.txt` have a first Russian version that needs checking (section 6).

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

**Recovery screen:** a first Russian version to check (section 6).

## 2. Fixed so far

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

- Names and abbreviations: `ABS`, `ADXL`, `AFC`, `Allwinner`, `Android logcat`, `BEACON`, `Bluetooth`, `Brother PT (Bluetooth)`, `Brother QL`, `Brother QL (Bluetooth)`, `CARTOGRAPHER`, `CPU`, `"CPU: "`, `Klipper: {}`, `Creality CFS`, `Creality K1`, `Creality K2 Plus`, `Elegoo Centauri Carbon`, `Ethernet`, `FlashForge Adventurer 5M`, `FlashForge Adventurer 5X`, `FlashForge Creator 5`, `FlashForge Creator 5 Pro`, `FlashForge IFS`, `Flowguard`, `HE`, `HELIXSCREEN`, `HEPA`, `Happy Hare MMU`, `HelixScreen`, `IP:`, `Kalico`, `Klipper`, `"Klipper: "`, `LOT-2024-001`, `MAC:`, `MCU`, `"MCU: "`, `MPC`, `MakeID (Bluetooth)`, `Moonraker`, `"Moonraker: "`, `Niimbot (Bluetooth)`, `OD`, `OK`, `OS`, `PA`, `PETG`, `PID`, `PLA`, `Phomemo (Bluetooth)`, `Phomemo M110`, `Polymaker`, `QGL`, `RAM`, `RH`, `RSS`, `RSS:`, `Raspberry Pi`, `Raspberry Pi (32-bit)`, `Shake&Tune`, `Snapmaker SnapSwap`, `Snapmaker U1`, `Spoolman`, `Sysfs`, `TPU`, `USB`, `WPA/WPA2`, `WPA3`, `Wi-Fi`, `Wi-Fi {}`, `XY`
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

243 keys come from Kiln OS, not from HelixScreen. All but two are at the end of `helixscreen-ru.yml`, after
`~{:.1f} Hz / turn` (in `helixscreen-en.yml` after the line `# Kiln OS (AD5X) strings from the Kiln HelixScreen
patches`), starting with `, corners {:+.3f} to {:+.3f}`. The other two are the chamber light lines
near the top (`Chamber light off when the screen sleeps` and the one after it). Keep IFS as IFS: it is the name of
the filament unit. (The 12 `Ad5x...` step names there are only used in log files; leave them.)

<details><summary>Setup wizard (64)</summary>

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

## 6. Recovery screen (recovery-ui/i18n/ru.txt)

The recovery screen is Kiln OS's rescue system. It uses the touch screen's language setting. Its strings are in
[recovery-ui/i18n/en.txt](../../recovery-ui/i18n/en.txt) (English) and [recovery-ui/i18n/ru.txt](../../recovery-ui/i18n/ru.txt)
(Russian). I wrote a first Russian version of all 155 lines; please check it and correct `ru.txt` directly:
each line is the id, one TAB, then the text. The rules are at the top of `en.txt`:

- keep the id; write the Russian after the TAB (keep the TAB, not spaces)
- keep `%s`, `%d`, `%u` in the same order and number; `%%` is a percent sign
- `\n` is a line break
- keep file paths and command names (`/data/ad5x/...`, `ad5x-update`, `SWUpdate`) as they are
- leave out the icons and "Kiln OS": the screen adds them (`recovery_title` is shown after "Kiln OS")
- the screen is small: keep a text about as long as the English, buttons especially
- the recovery font only holds the characters the texts use; if you add a new one, that's fine, I regenerate the font

The lines I am least sure of:

- `recovery_row` = `Версия`: the row shows the recovery's release number. `Восстановление` does not fit the 120 px label.
- `update_one` / `update_many` = `обновление` / `обновл.`: the screen has only these two forms after a number, so the
  second is shortened to fit both 2-4 (обновления) and 5+ (обновлений).
- Stock firmware = `родная прошивка`, as in zMod's Russian wiki ("Родная прошивка").
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
  = `Вернуть родную`
- `restore_stock_fw_btn`: `Restore stock firmware…`
  = `Вернуть родную прошивку…`
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
  = `Возврат родной прошивки`
- `restore_stock_q`: `Restore stock firmware?`
  = `Вернуть родную прошивку?`
- `stock_q_text`: `Writes the saved stock Flashforge system into the main slot (B) and makes it the one that starts. Kiln OS in slot B is replaced.`
  = `Записывает сохранённую родную систему Flashforge в основной слот (B) и делает её системой для запуска. Kiln OS в слоте B будет заменена.`
- `stock_q_text2`: `Slot B will be overwritten with the stock firmware. Keep the printer powered until it is done.`
  = `Слот B будет перезаписан родной прошивкой. Не выключайте принтер до конца.`
- `stock_saved_note`: `A saved stock system was found in /data/ad5x/stock.`
  = `Сохранённая родная система найдена в /data/ad5x/stock.`
- `stock_none_note`: `No saved stock system in /data/ad5x/stock: it is made by ad5x-update --replace-stock when Kiln OS is installed.`
  = `В /data/ad5x/stock нет сохранённой родной системы: её создаёт ad5x-update --replace-stock при установке Kiln OS.`
- `restore_stock_firmware`: `Restore stock firmware`
  = `Вернуть родную прошивку`
- `stock_back_title`: `Back to Flashforge's firmware`
  = `Возврат к прошивке Flashforge`
- `stock_text`: `Writes the stock system saved on the printer when Kiln OS was installed back into the main slot (B), checks it, and points the boot flag at it. This recovery stays as it is.`
  = `Записывает родную систему, сохранённую на принтере при установке Kiln OS, обратно в основной слот (B), проверяет её и направляет на неё флаг загрузки. Система восстановления остаётся как есть.`
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
