wrote eval_logs_stl/nl/episodes.csv (180 episodes)
wrote eval_logs_stl/stl_nl/episodes.csv (180 episodes)
wrote eval_logs_stl/stl/episodes.csv (180 episodes)

thresholds: Thresholds(still_speed=0.01, still_spin=0.25, part_still=0.01, base_speed=0.02, base_turn=0.05, disturb_disp=0.02, disturb_rot=10.0, disturb_tilt=10.0, fixture_changed=0.2, grasp_lift=0.02)  velocities: sim  Disturbed reference: settle

**Summary** (episodes that passed / episodes run; 95% Wilson range of the pass rate in brackets)

| Prompt | Task success | Deadline met | Clean success | Full STL |
| --- | --- | --- | --- | --- |
| `nl` | 78/180 [36–51%] | 28/180 [11–22%] | 75/180 [35–49%] | 28/180 [11–22%] |
| `stl_nl` | 23/180 [9–18%] | 1/180 [0–3%] | 23/180 [9–18%] | 1/180 [0–3%] |
| `stl` | 9/180 [3–9%] | 0/180 [0–2%] | 9/180 [3–9%] | 0/180 [0–2%] |

**Per task** (out of the episodes run; cells are `nl` / `stl_nl` / `stl`)

| # | Task | Type | Task success | Clean success | Deadline met / Full STL |
| --- | --- | --- | --- | --- | --- |
| 0 | CloseBlenderLid | P | 2 / 1 / 1 | 2 / 1 / 1 | 0 / 0 · 0 / 0 · 0 / 0 |
| 1 | CloseFridge | F | 5 / 4 / 0 | 5 / 4 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 2 | CloseToasterOvenDoor | F | 2 / 0 / 0 | 2 / 0 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 3 | CoffeeSetupMug | P | 3 / 0 / 0 | 3 / 0 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 4 | NavigateKitchen | N | 1 / 0 / 0 | 1 / 0 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 5 | OpenCabinet | F | 5 / 0 / 0 | 4 / 0 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 6 | OpenDrawer | F | 7 / 3 / 2 | 6 / 3 / 2 | 6 / 6 · 0 / 0 · 0 / 0 |
| 7 | OpenStandMixerHead | F | 3 / 0 / 2 | 3 / 0 / 2 | 3 / 3 · 0 / 0 · 0 / 0 |
| 8 | PickPlaceCounterToCabinet | P | 5 / 2 / 0 | 5 / 2 / 0 | 5 / 5 · 0 / 0 · 0 / 0 |
| 9 | PickPlaceCounterToStove | P | 6 / 0 / 1 | 6 / 0 / 1 | 4 / 4 · 0 / 0 · 0 / 0 |
| 10 | PickPlaceDrawerToCounter | P | 4 / 0 / 0 | 4 / 0 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 11 | PickPlaceSinkToCounter | P | 7 / 5 / 0 | 7 / 5 / 0 | 6 / 6 · 1 / 1 · 0 / 0 |
| 12 | PickPlaceToasterToCounter | P | 6 / 0 / 0 | 6 / 0 / 0 | 1 / 1 · 0 / 0 · 0 / 0 |
| 13 | SlideDishwasherRack | F | 8 / 4 / 1 | 8 / 4 / 1 | 0 / 0 · 0 / 0 · 0 / 0 |
| 14 | TurnOffStove | F | 3 / 0 / 0 | 2 / 0 / 0 | 0 / 0 · 0 / 0 · 0 / 0 |
| 15 | TurnOnElectricKettle | F | 4 / 2 / 0 | 4 / 2 / 0 | 2 / 2 · 0 / 0 · 0 / 0 |
| 16 | TurnOnMicrowave | F | 4 / 1 / 0 | 4 / 1 / 0 | 1 / 1 · 0 / 0 · 0 / 0 |
| 17 | TurnOnSinkFaucet | F | 3 / 1 / 2 | 3 / 1 / 2 | 0 / 0 · 0 / 0 · 0 / 0 |

**Paired by seed** (exact McNemar; gained = passes with the second prompt only, lost = the first only)

| Comparison | Metric | gained | lost | p |
| --- | --- | --- | --- | --- |
| `stl_nl` vs `nl` | Task success | 7 | 62 | 4.1e-12 |
| `stl_nl` vs `nl` | Deadline met | 1 | 28 | 1.1e-07 |
| `stl_nl` vs `nl` | Clean success | 8 | 60 | 5.7e-11 |
| `stl_nl` vs `nl` | Full STL | 1 | 28 | 1.1e-07 |
| `stl` vs `nl` | Task success | 3 | 72 | 3.7e-18 |
| `stl` vs `nl` | Deadline met | 0 | 28 | 7.5e-09 |
| `stl` vs `nl` | Clean success | 3 | 69 | 2.6e-17 |
| `stl` vs `nl` | Full STL | 0 | 28 | 7.5e-09 |
| `stl` vs `stl_nl` | Task success | 6 | 20 | 0.0094 |
| `stl` vs `stl_nl` | Deadline met | 0 | 1 | 1 |
| `stl` vs `stl_nl` | Clean success | 6 | 20 | 0.0094 |
| `stl` vs `stl_nl` | Full STL | 0 | 1 | 1 |

**Why each deadline failure happened**

| Cause | `nl` | `stl_nl` | `stl` |
| --- | --- | --- | --- |
| done by T, gripper near / touching at the end | 7 | 0 | 0 |
| done by T, gripper near / touching until after T | 4 | 1 | 1 |
| done by T, settled only after T | 4 | 1 | 0 |
| done by T, undone at the end | 1 | 0 | 0 |
| first done after T | 34 | 20 | 8 |
| never done | 102 | 157 | 171 |
| **total** | **152** | **179** | **180** |

**Other objects disturbed** (episodes with at least one o in O disturbed; tasks with O non-empty)

| Task | `nl` | `stl_nl` | `stl` | objects (all prompts) |
| --- | --- | --- | --- | --- |
| CloseFridge | 0/10 | 0/10 | 8/10 | door_obj ×8 |
| OpenCabinet | 1/10 | 0/10 | 2/10 | door_obj ×2, distr_counter_1 ×1 |
| OpenDrawer | 1/10 | 0/10 | 0/10 | drawer_obj ×1 |
| PickPlaceCounterToCabinet | 0/10 | 0/10 | 4/10 | distr_cab ×4 |
| PickPlaceDrawerToCounter | 0/10 | 0/10 | 4/10 | distr ×4 |
| PickPlaceSinkToCounter | 0/10 | 0/10 | 4/10 | distr_counter ×4 |
| TurnOffStove | 1/10 | 0/10 | 2/10 | cookware ×3 |
| TurnOnMicrowave | 0/10 | 0/10 | 0/10 |  |
| TurnOnSinkFaucet | 1/10 | 1/10 | 1/10 | distr_counter_0 ×2, distr_counter_1 ×2 |

**Diagnostics** (counts)

| Prompt | pushed in (P) | bumped (F) | fixture changed | tilt-only undisturbed | success at end |
| --- | --- | --- | --- | --- | --- |
| `nl` | 0/70 | 0/100 | 14/180 | 176/180 | 76/180 |
| `stl_nl` | 0/70 | 0/100 | 8/180 | 180/180 | 23/180 |
| `stl` | 0/70 | 0/100 | 11/180 | 157/180 | 8/180 |

pairing: the same seed gives the same scene under every prompt for 180/180 (task, seed) pairs

consistency: steps == task limit in 540/540; rtamt == numpy in 540/540; lerobot-eval success == any(success) in 540/540
