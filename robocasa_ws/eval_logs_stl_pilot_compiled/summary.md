wrote eval_logs_stl_pilot/nl/episodes.csv (18 episodes)

thresholds: Thresholds(still_speed=0.01, still_spin=0.25, part_still=0.01, base_speed=0.02, base_turn=0.05, disturb_disp=0.02, disturb_rot=10.0, disturb_tilt=10.0, fixture_changed=0.02, grasp_lift=0.02)  velocities: sim  Disturbed reference: t0

**Summary** (episodes that passed / episodes run; 95% Wilson range of the pass rate in brackets)

| Prompt | Task success | Deadline met | Clean success | Full STL |
| --- | --- | --- | --- | --- |
| `nl` | 0/18 [0–18%] | 0/18 [0–18%] | 0/18 [0–18%] | 0/18 [0–18%] |

**Per task** (out of the episodes run; cells are `nl`)

| # | Task | Type | Task success | Clean success | Deadline met / Full STL |
| --- | --- | --- | --- | --- | --- |
| 0 | CloseBlenderLid | P | 0 | 0 | 0 / 0 |
| 1 | CloseFridge | F | 0 | 0 | 0 / 0 |
| 2 | CloseToasterOvenDoor | F | 0 | 0 | 0 / 0 |
| 3 | CoffeeSetupMug | P | 0 | 0 | 0 / 0 |
| 4 | NavigateKitchen | N | 0 | 0 | 0 / 0 |
| 5 | OpenCabinet | F | 0 | 0 | 0 / 0 |
| 6 | OpenDrawer | F | 0 | 0 | 0 / 0 |
| 7 | OpenStandMixerHead | F | 0 | 0 | 0 / 0 |
| 8 | PickPlaceCounterToCabinet | P | 0 | 0 | 0 / 0 |
| 9 | PickPlaceCounterToStove | P | 0 | 0 | 0 / 0 |
| 10 | PickPlaceDrawerToCounter | P | 0 | 0 | 0 / 0 |
| 11 | PickPlaceSinkToCounter | P | 0 | 0 | 0 / 0 |
| 12 | PickPlaceToasterToCounter | P | 0 | 0 | 0 / 0 |
| 13 | SlideDishwasherRack | F | 0 | 0 | 0 / 0 |
| 14 | TurnOffStove | F | 0 | 0 | 0 / 0 |
| 15 | TurnOnElectricKettle | F | 0 | 0 | 0 / 0 |
| 16 | TurnOnMicrowave | F | 0 | 0 | 0 / 0 |
| 17 | TurnOnSinkFaucet | F | 0 | 0 | 0 / 0 |

**Why each deadline failure happened**

| Cause | `nl` |
| --- | --- |
| never done | 18 |
| **total** | **18** |

**Other objects disturbed** (episodes with at least one o in O disturbed; tasks with O non-empty)

| Task | `nl` | objects (all prompts) |
| --- | --- | --- |
| CloseFridge | 0/1 |  |
| OpenCabinet | 0/1 |  |
| OpenDrawer | 0/1 |  |
| PickPlaceCounterToCabinet | 0/1 |  |
| PickPlaceDrawerToCounter | 0/1 |  |
| PickPlaceSinkToCounter | 1/1 | distr_counter ×1 |
| TurnOffStove | 0/1 |  |
| TurnOnMicrowave | 0/1 |  |
| TurnOnSinkFaucet | 0/1 |  |

**Diagnostics** (counts)

| Prompt | pushed in (P) | bumped (F) | fixture changed | tilt-only undisturbed | success at end |
| --- | --- | --- | --- | --- | --- |
| `nl` | 0/7 | 0/10 | 13/18 | 17/18 | 0/18 |

consistency: steps == task limit in 18/18; rtamt == numpy in 18/18; lerobot-eval success == any(success) in 18/18
