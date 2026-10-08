# IPDS Sensor Node: KiCad PCB

Carrier board for the IPDS sensor node: an **ESP32-DevKitC (38-pin)** plus plug-in **MPU6050**, **DS3231 RTC** and **NEO-6M GPS** breakout modules. Every module sits in a female header, so nothing is soldered to the modules themselves.

<p align="center"><img src="fabrication/pcb_render_top.png" alt="IPDS sensor node PCB, top view" width="720"></p>

**Board:** 117 × 68 mm · 2 layers · 1.6 mm FR4 · GND pour on both sides · 4 × M3 mounting holes
**Made with:** KiCad 10.0 (open with KiCad 10 or newer)

### Verification status

Checked with `kicad-cli` (KiCad 10.0.6):

| Check | Result |
|---|---|
| ERC (schematic) | **0 violations** |
| DRC (PCB, all severities) | **0 violations**, **0 unconnected items** |
| Schematic ↔ PCB parity | **0 issues** |

```bash
kicad-cli sch erc --severity-all IPDS_SensorNode.kicad_sch
kicad-cli pcb drc --severity-all --schematic-parity IPDS_SensorNode.kicad_pcb
```

---

## Files

| File | Description |
|---|---|
| `IPDS_SensorNode.kicad_pro` | Project settings and design rules |
| `IPDS_SensorNode.kicad_sch` | Schematic |
| `IPDS_SensorNode.kicad_pcb` | PCB layout |
| `IPDS.kicad_sym` | Project symbols: ESP32-DevKitC and the three breakout modules (named pins) |
| `IPDS.pretty/` | Project footprint: ESP32-DevKitC 38-pin socket |
| `fabrication/IPDS_SensorNode_gerbers.zip` | Gerbers + Excellon drill files, ready to upload to a PCB fab |
| `fabrication/IPDS_SensorNode_schematic.pdf` | Schematic as PDF |
| `fabrication/IPDS_SensorNode_BOM.csv` | Bill of materials |

---

## Connections

| Net | ESP32 pin | Connected to |
|---|---|---|
| `+3V3` | 3V3 (onboard regulator) | MPU VCC, MPU **AD0**, RTC VCC, GPS VCC, R1, R2, C1, C2 |
| `GND` | GND ×3 | All modules, J1 pin 2, C1, C2 |
| `+5V` | 5V | D1 cathode (external 5 V input) |
| `SDA` | GPIO21 | MPU SDA, RTC SDA, R1 4.7 kΩ pull-up |
| `SCL` | GPIO22 | MPU SCL, RTC SCL, R2 4.7 kΩ pull-up |
| `ESP_TX2` | GPIO17 (TX2) | GPS **RX** |
| `ESP_RX2` | GPIO16 (RX2) | GPS **TX** |
| `VIN_EXT` | n/a | J1 pin 1 → D1 anode |

### I²C addresses

| Device | Address | Note |
|---|---|---|
| DS3231 RTC | `0x68` | fixed |
| AT24C32 EEPROM (on the ZS-042 board) | `0x57` | unused |
| MPU6050 | **`0x69`** | AD0 is tied to 3V3 on this PCB, because `0x68` is already taken by the DS3231 |

The sensor firmware (`ESP_32_Code/esp_32_final`) uses exactly these pins and addresses. GPS UART runs at 9600 baud, 8N1.

### Module pin order (match the silkscreen)

| Socket | Module | Pin order (pin 1 = square pad, top) |
|---|---|---|
| U2 (1×8) | GY-521 MPU6050 | VCC, GND, SCL, SDA, XDA, XCL, AD0, INT |
| U3 (1×6) | ZS-042 DS3231 | 32K, SQW, SCL, SDA, VCC, GND |
| U4 (1×4) | GY-NEO6MV2 | VCC, RX, TX, GND |

Breakout boards from different sellers sometimes order their pins differently. **Check your module's printed labels against the table before plugging it in.**

---

## Before you order

1. **Measure your ESP32 board.** The footprint expects the two pin rows **25.4 mm (1.0") apart**, as on Espressif's DevKitC V4 and most 38-pin clones. Some "narrow" clones are 22.86 mm; if yours is, move the right-hand row in `IPDS.pretty`.
2. **Power:** feed 5 V into J1 (e.g. a car USB adapter) **or** use the DevKit's USB port. If your DevKit has no diode on its USB 5 V line, don't connect both at once: D1 stops J1 from being back-fed, but USB could be back-fed from J1.
3. **ZS-042 with a CR2032:** the module has a charging circuit meant for rechargeable LIR2032 cells. With a normal CR2032, remove its 200 Ω resistor (or the diode next to it).

## Bill of materials

| Qty | Ref | Part | Notes |
|---|---|---|---|
| 1 | U1 | ESP32-DevKitC 38-pin | plus **2 × 1×19 female headers**, 2.54 mm |
| 1 | U2 | GY-521 MPU6050 module | 1×8 female header |
| 1 | U3 | ZS-042 DS3231 module + CR2032 | 1×6 female header |
| 1 | U4 | GY-NEO6MV2 NEO-6M GPS module + antenna | 1×4 female header |
| 1 | J1 | Phoenix MKDS 1,5/2-5.08 screw terminal | or any 5.08 mm 2-pin terminal |
| 1 | D1 | SS14 Schottky diode, SMA | 1 A, 40 V |
| 2 | R1, R2 | 4.7 kΩ, 0805 | I²C pull-ups |
| 1 | C1 | 100 nF, 0805 | decoupling |
| 1 | C2 | 10 µF, 0805, ≥10 V | bulk |
| 4 | — | M3 standoffs + screws | mounting |

## Ordering the PCB

Upload `fabrication/IPDS_SensorNode_gerbers.zip` to JLCPCB, PCBWay or a similar fab with the defaults: 2 layers, 1.6 mm, HASL, 1 oz copper. All tracks are ≥ 0.25 mm and clearances ≥ 0.2 mm, so standard (cheapest) capabilities are enough.

To regenerate the outputs after editing: **File → Fabrication Outputs → Gerbers** and **Drill Files** in the PCB editor, after re-running **Inspect → Design Rules Checker**.
