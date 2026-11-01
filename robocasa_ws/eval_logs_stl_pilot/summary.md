wrote eval_logs_stl_pilot/nl/episodes.csv (18 episodes)

thresholds: Thresholds(still_speed=0.01, still_spin=0.25, part_still=0.01, base_speed=0.02, base_turn=0.05, disturb_disp=0.02, disturb_rot=10.0, disturb_tilt=10.0, fixture_changed=0.2, grasp_lift=0.02)  velocities: sim  Disturbed reference: settle

**Summary** (episodes that passed / episodes run; 95% Wilson range of the pass rate in brackets)

| Prompt | Task success | Deadline met | Clean success | Full STL |
| --- | --- | --- | --- | --- |
| `nl` | 7/18 [20–61%] | 3/18 [6–39%] | 6/18 [16–56%] | 3/18 [6–39%] |

**Per task** (out of the episodes run; cells are `nl`)

| # | Task | Type | Task success | Clean success | Deadline met / Full STL |
| --- | --- | --- | --- | --- | --- |
| 0 | CloseBlenderLid | P | 0 | 0 | 0 / 0 |
| 1 | CloseFridge | F | 1 | 1 | 0 / 0 |
| 2 | CloseToasterOvenDoor | F | 0 | 0 | 0 / 0 |
| 3 | CoffeeSetupMug | P | 0 | 0 | 0 / 0 |
| 4 | NavigateKitchen | N | 0 | 0 | 0 / 0 |
| 5 | OpenCabinet | F | 1 | 0 | 0 / 0 |
| 6 | OpenDrawer | F | 1 | 1 | 1 / 1 |
| 7 | OpenStandMixerHead | F | 1 | 1 | 1 / 1 |
| 8 | PickPlaceCounterToCabinet | P | 1 | 1 | 1 / 1 |
| 9 | PickPlaceCounterToStove | P | 0 | 0 | 0 / 0 |
| 10 | PickPlaceDrawerToCounter | P | 1 | 1 | 0 / 0 |
| 11 | PickPlaceSinkToCounter | P | 0 | 0 | 0 / 0 |
| 12 | PickPlaceToasterToCounter | P | 0 | 0 | 0 / 0 |
| 13 | SlideDishwasherRack | F | 1 | 1 | 0 / 0 |
| 14 | TurnOffStove | F | 0 | 0 | 0 / 0 |
| 15 | TurnOnElectricKettle | F | 0 | 0 | 0 / 0 |
| 16 | TurnOnMicrowave | F | 0 | 0 | 0 / 0 |
| 17 | TurnOnSinkFaucet | F | 0 | 0 | 0 / 0 |

**Why each deadline failure happened**

| Cause | `nl` |
| --- | --- |
| done by T, gripper near / touching at the end | 2 |
| first done after T | 2 |
| never done | 11 |
| **total** | **15** |

**Other objects disturbed** (episodes with at least one o in O disturbed; tasks with O non-empty)

| Task | `nl` | objects (all prompts) |
| --- | --- | --- |
| CloseFridge | 0/1 |  |
| OpenCabinet | 1/1 | door_obj ×1 |
| OpenDrawer | 0/1 |  |
| PickPlaceCounterToCabinet | 0/1 |  |
| PickPlaceDrawerToCounter | 0/1 |  |
| PickPlaceSinkToCounter | 0/1 |  |
| TurnOffStove | 0/1 |  |
| TurnOnMicrowave | 0/1 |  |
| TurnOnSinkFaucet | 1/1 | distr_counter_0 ×1, distr_counter_1 ×1 |

**Diagnostics** (counts)

| Prompt | pushed in (P) | bumped (F) | fixture changed | tilt-only undisturbed | success at end |
| --- | --- | --- | --- | --- | --- |
| `nl` | 0/7 | 0/10 | 1/18 | 16/18 | 7/18 |

consistency: steps == task limit in 18/18; rtamt == numpy in 18/18; lerobot-eval success == any(success) in 18/18
