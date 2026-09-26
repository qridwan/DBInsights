# Results

*Draft generated from stored results. Every number is looked up, not typed; see the appendix.*

## 0. How to read this chapter

Two kinds of evidence are reported and are **never combined into one claim**.

- **Controlled experiment (M5).** Two test applications with 46 problems injected by the author and recorded in a ground-truth manifest. Each of seven configurations was run 10 times per application. It measures what each evidence layer contributes when the answer is known.
- **Real-world validation (M6).** Open-source projects the author did not write, with no known answer. It measures precision only, and only after human labelling (section 8).

Two properties of the controlled experiment shape every number below.

1. **Accuracy is deterministic.** For a fixed database, source tree and manifest, a configuration finds the same problems on every repetition. Repetitions therefore add no variance to accuracy; they show that it is stable and are informative only for timing. Accuracy uncertainty comes from the finite set of 46 problems, so accuracy intervals are bootstrap intervals over problems, and paired comparisons are exact McNemar tests on per-problem outcomes.
2. **The problems were injected by the author, who also built the analyzer.** The injected types mirror what the rules look for. Results show that each layer finds what it was designed to find; they are not an estimate of how common these problems are anywhere.

The experiment ran on code with uncommitted changes (commit `4a2a347`, working-tree hash `26a53e46f8be`), recorded so the result can be tied to the exact code.

## 1. RQ1: how effectively does the hybrid framework detect problems?

Configuration **C3** enables every layer: static ORM analysis, SQL analysis, the declared schema, the actual schema, runtime capture and data-quality statistics. Pooled over both applications it found 33 of 46 problems.

- Recall: 71.7% (95% CI 58.7% to 84.8%)
- Precision: 94.3% (95% CI 85.7% to 100.0%)
- F1: 81.5% (95% CI 71.5% to 89.3%)
- False-positive rate: 0.5%, with 2 false positives among 35 scored findings.

| Config | Precision | Recall | F1 | False-positive rate | Problems found | Scored findings |
|---|---|---|---|---|---|---|
| A | no findings | 0.0% (95% CI 0.0% to 0.0%) | undefined | 0.00% | 0 of 46 | 0 |
| A-log (sensitivity) | 20.7% (95% CI 6.9% to 37.9%) | 13.0% (95% CI 4.3% to 23.9%) | 16.0% (95% CI 6.1% to 24.0%) | 6.30% | 6 of 46 | 29 |
| B1 | 100.0% (95% CI 100.0% to 100.0%) | 26.1% (95% CI 13.0% to 39.1%) | 41.4% (95% CI 23.1% to 56.2%) | 0.00% | 12 of 46 | 12 |
| B2 | 100.0% (95% CI 100.0% to 100.0%) | 37.0% (95% CI 23.9% to 50.0%) | 54.0% (95% CI 38.6% to 66.7%) | 0.00% | 17 of 46 | 17 |
| C1 | 100.0% (95% CI 100.0% to 100.0%) | 45.7% (95% CI 30.4% to 60.9%) | 62.7% (95% CI 46.7% to 75.7%) | 0.00% | 21 of 46 | 21 |
| C2 | 100.0% (95% CI 100.0% to 100.0%) | 45.7% (95% CI 30.4% to 60.9%) | 62.7% (95% CI 46.7% to 75.7%) | 0.00% | 21 of 46 | 21 |
| C3 | 94.3% (95% CI 85.7% to 100.0%) | 71.7% (95% CI 58.7% to 84.8%) | 81.5% (95% CI 71.5% to 89.3%) | 0.55% | 33 of 46 | 35 |

Intervals are 95% bootstrap intervals over the benchmark's problems.

**By problem type** (recall, mean over repetitions):

| Problem type | Problems | A | A-log | B1 | B2 | C1 | C2 | C3 |
|---|---|---|---|---|---|---|---|---|
| `declared_index_not_applied` | 2 | 0% | 0% | 0% | 0% | 100% | 100% | 100% |
| `distribution_shift` | 3 | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| `duplicate_spike` | 3 | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| `excessive_relation_loading` | 6 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| `index_not_declared` | 2 | 0% | 0% | 0% | 0% | 100% | 100% | 100% |
| `missing_index` | 6 | 0% | 0% | 0% | 83% | 83% | 83% | 83% |
| `n_plus_one` | 6 | 0% | 0% | 100% | 100% | 100% | 100% | 100% |
| `null_spike` | 3 | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| `orphaned_foreign_key` | 3 | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| `repeated_identical_query` | 6 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| `unpaginated_find_many` | 6 | 0% | 100% | 100% | 100% | 100% | 100% | 100% |

**What the result says.** The hybrid finds most of what was injected, with few false positives. It finds every problem of eight of the eleven problem types, and 5 of 6 of a ninth. The data-quality types are found only once the data layer is on (the step from C2 to C3).

**What it does not say.**
- **Two problem types are missed by every configuration.** `excessive_relation_loading` and `repeated_identical_query` have 6 and 6 problems each, and recall is 0% and 0% in C3. The system has no rule for them, so this is a coverage gap, not a near miss.
- One `missing_index` problem is missed by every configuration that has the ORM layer (83.3% recall). This is a known limitation of the analyzer's handling of a shorthand `{ where }` filter, left unfixed on purpose so the results describe the system as built.
- **Precision below 100% comes from one type.** `duplicate_spike` has 2 false positives (precision 60%). Both are duplicate-rate findings on the `Post` table, in columns the manifest does not label. Whether they are real side effects of the injection that the manifest failed to record was not adjudicated; the manifest was not edited after the results were seen, so both count as false positives.
- **This is a comparison with layers of the same system, not with existing tools.** No other tool was run.

## 2. RQ2: does ORM-aware source analysis find problems that SQL analysis alone misses?

Two configurations answer this. **A** is static SQL analysis alone, over the SQL text in the repository. **B1** adds ORM-aware source analysis.

- A found 0 of 46 problems. B1 found 12, with precision 100% and recall 26.1% (95% CI 13.0% to 39.1%).
- Paired on the same problems, B1 found 12 that A missed and A found 0 that B1 missed (exact McNemar p = 4.9e-04, not part of the corrected family; recall difference 26.1% (95% CI 13.0% to 39.1%)).

**What the result says.** On these Prisma applications, N+1 patterns and unpaginated queries are visible in source through the ORM's API and are not visible as SQL text.

**What it does not say.** The comparison is close to definitional. Prisma builds its SQL at run time, so SQL analysis of the repository finds almost nothing to analyse; A finding zero problems says more about the baseline's input than about SQL analysis as a technique. To avoid a strawman baseline a sensitivity arm, **A-log**, gives the SQL analyzer the statements the application actually issued (as a query log would). A-log found 6 problems with precision 21%. The hybrid C3 still found 27 problems that A-log missed and lost 0 (recall difference 58.7% (95% CI 43.5% to 71.7%)). A-log is an addition to the plan and is reported separately from the six configurations.

## 3. RQ3: does combining static analysis with runtime behaviour improve precision and recall?

This is the C1 to C2 step: runtime capture added to everything else.

- Problems gained by runtime: **0**, lost: **0**. Precision and recall are identical (45.7% recall and 100% precision in both), exact McNemar p = 1.000.
- Confidence of the matching finding, over the 21 problems both found: mean 2.86 without runtime, 2.86 with it (scale 1 to 3), Wilcoxon p = 1.000.
- Cost: 2.22 s to 2.36 s CPU per application run (Wilcoxon p = 5.7e-06, Cliff's delta 0.70). Wall time rises from 2.5 s to 9.8 s, because runtime capture drives real traffic.

**This result contradicts hypothesis H3** ("runtime analysis provides stronger evidence for performance findings than static analysis alone"). In this experiment runtime evidence added no detections and no confidence, and cost time.

**Why, and what this does not show.** The runtime layer has a single rule, runtime N+1 detection. It fires on the problems that static analysis already finds, so it corroborates rather than adds. The two problem types only runtime behaviour could reveal have no runtime rule (RQ1). The result therefore does not show that runtime evidence cannot help; it shows that, with one runtime rule and problems that are also statically visible, it did not help here. Runtime findings do appear in the evidence chain of the findings they corroborate (the dashboard shows this chain for each finding), which is a qualitative benefit the recall and confidence measures do not capture.

## 4. RQ4: can statistical anomaly detection identify unexpected changes?

**Data characteristics.** Three detectors (z-score, IQR, moving average) learn an expected range for each column's null rate, duplicate rate and value distribution from that column's own history, and a majority vote flags a window. Adding the data layer (C2 to C3) raised recall from 45.7% to 71.7%. Every injected `null_spike`, `distribution_shift` and `duplicate_spike` problem was found (recall 100%, 100% and 100%, on 3, 3 and 3 problems), at the price of the 2 duplicate-rate false positives above.

**False alarms on clean history.** Walking forward over history known to be clean, each window judged only against earlier ones, the majority vote raised 5 increase alarms in 515 evaluations (1.0%): 3 of 294 on the e-commerce application and 2 of 221 on the blog. Individually the detectors raised 5 (z-score), 13 (IQR) and 4 (moving average) increase alarms, so the IQR detector is the noisiest and the vote suppresses part of that.

**What the result says.** Learned, per-column ranges detected all injected data-quality changes without a fixed threshold, at a low false-alarm rate on clean history.

**What it does not say.**
- **RQ4 also asks about query behaviour, and that half is not measured.** No statistical detector runs over query behaviour. Runtime N+1 detection is rule-based, not statistical.
- The injected changes are large (a null rate moved from a few percent to over half, a distribution moved by tens of points). Sensitivity to small changes was not measured.
- The clean history is 12 synthetic windows of 30 days from a deterministic seed, which is more regular than production data.

## 5. RQ5: what trade-offs exist between accuracy, false positives and overhead?

| Config | Time to first detection | CPU per run | Wall time per run |
|---|---|---|---|
| A | no detections | 0.01 s (95% CI 0.01 to 0.01) | 0.01 s (95% CI 0.01 to 0.01) |
| A-log | 3.69 s (95% CI 3.57 to 3.82) | 0.53 s (95% CI 0.52 to 0.55) | 7.39 s (95% CI 7.14 to 7.64) |
| B1 | 1.06 s (95% CI 1.02 to 1.11) | 3.94 s (95% CI 3.87 to 4.01) | 2.14 s (95% CI 2.06 to 2.23) |
| B2 | 1.02 s (95% CI 0.99 to 1.05) | 4.39 s (95% CI 4.32 to 4.46) | 2.44 s (95% CI 2.38 to 2.51) |
| C1 | 1.06 s (95% CI 1.03 to 1.10) | 4.44 s (95% CI 4.31 to 4.56) | 2.50 s (95% CI 2.40 to 2.59) |
| C2 | 1.05 s (95% CI 1.00 to 1.11) | 4.71 s (95% CI 4.58 to 4.84) | 9.80 s (95% CI 9.28 to 10.32) |
| C3 | 2.36 s (95% CI 2.32 to 2.40) | 4.82 s (95% CI 4.77 to 4.86) | 9.82 s (95% CI 9.60 to 10.03) |

Intervals are 95% t-intervals over repetitions; time to first detection is the mean over detected problems, in seconds from the start of the run.

- **False positives.** The ablation configurations up to C2 have a false-positive rate of 0.00%; C3 has 0.55%. Adding the data layer raised recall from 45.7% to 71.7% and introduced every false positive among the six ablation configurations. The sensitivity arm A-log has a higher rate (6.3%), because it judges SQL text without the schema or source context.
- **Analysis cost.** C3 uses 4.82 s CPU per run against 4.39 s for B2, which needs no database, and 0.013 s for A, which finds nothing.
- **Runtime cost without a return.** The step to C2 adds cost and no accuracy (RQ3).

**Collector overhead.** The runtime collector was switched on and off in ABBA order. Every stored session with at least ten repetitions is reported, because the measured overhead varies between sessions and no single session should stand for the rest (5 sessions):

| Session | App | Repetitions | Median overhead (ms) | Median overhead (ratio) | Median latency, collector on (ms) | off (ms) |
|---|---|---|---|---|---|---|
| b8a94355 | ecommerce | 10 | 0.38 | 9.8% | 4.23 | 3.85 |
| fd39aa1a | blog | 10 | 0.18 | 4.6% | 4.19 | 4.00 |
| 12181824 | ecommerce | 10 | 0.57 | 16.4% | 4.07 | 3.50 |
| 2738215a | blog | 10 | 0.26 | 7.3% | 3.81 | 3.55 |
| 401bc8a2 | ecommerce | 10 | 0.45 | 13.2% | 3.86 | 3.41 |

Across sessions the median added latency per request was 0.38 to 0.57 ms on the e-commerce application (9.8% to 16.4% of median latency) and 0.18 to 0.26 ms on the blog (4.6% to 7.3%).

**What the result says.** The collector adds a fraction of a millisecond to a median request of about four milliseconds.

**What it does not say.** The requests are tiny, from a fixed local load script against a local database; the overhead ratio would look different for slower queries. The applications are small. Several sessions came from different code states, which is part of why the range is reported.

## 6. RQ6: how far does the declared schema diverge from the actual one?

The declared schema (`schema.prisma`) and the actual schema (the live database catalog) are separate evidence sources and were never merged. Four divergences were injected, two in each direction: an index in the database that the schema does not declare (`index_not_declared`), and an index the schema declares that the database lacks (`declared_index_not_applied`).

- **What the live database adds (B2 to C1).** C1 found 4 problems B2 missed and lost 0 (recall difference 8.7% (95% CI 2.2% to 17.4%)). The exact test gives p = 0.125 (Holm-corrected 0.250), **not significant**. The exact test cannot go below p = 0.0625 with only four discordant problems, so the test has too little power to declare significance whatever the effect; the direction is consistent (all four in C1's favour) and the interval excludes zero.
- **What the declared schema adds (B1 to B2, hypothesis H5's comparison).** B2 found 5 problems B1 missed and lost 0 (recall difference 10.9% (95% CI 2.2% to 21.7%)); exact p = 0.062, Holm-corrected 0.188, **not significant** for the same reason. All five are `missing_index` problems, which need the declared schema to judge.
- **Hypothesis H5 stated directly.** H5 claims that a substantial share of the index findings obtainable from the live database are also obtainable from the declared schema alone. Of the 9 index problems obtainable with the database, 5 were also obtainable from source and the declared schema alone: **55.6% (95% CI 26.7% to 81.1%)** (Wilson interval). By type: 5 of 5 `missing_index`, 0 of 2 `index_not_declared`, 0 of 2 `declared_index_not_applied`.

**What the result says.** A database connection adds exactly the divergence findings: the declared schema alone cannot see an index that is only in the database, or only in the schema file. The declared schema by itself carries the missing-index findings that need no database.

**What it does not say.**
- **The H5 share is a property of the benchmark, not of the world.** The denominator was fixed by how many problems of each kind were injected; with more divergence instances the share would be lower, with fewer it would be higher. It is not an estimate of how often real projects diverge. The real-world divergence rate is the quantity that would answer RQ6, and it has not been measured (section 8).
- **The cost of divergence to declared-only findings was not observed.** In the controlled applications no declared-only finding was a false positive because of divergence (B2 precision 100%).
- Two instances per divergence direction is a small number.

## 7. The hypotheses at a glance

| Hypothesis | Result | Where |
|---|---|---|
| H1: hybrid detects a broader range than SQL alone | **Supported.** C3 found 33 problems A missed, lost 0 (Holm p = 9.3e-10). Against the stronger A-log baseline it still held (27 gained, 0 lost) | section 2 |
| H2: ORM-aware analysis improves anti-pattern detection | **Supported** on N+1 and unpaginated queries (12 gained), with the caveat that the baseline cannot see the ORM | section 2 |
| H3: runtime gives stronger evidence than static alone | **Contradicted.** 0 gained, no change in confidence, extra cost | section 3 |
| H4: anomaly detection finds meaningful changes | **Supported for data characteristics**; not tested for query behaviour | section 4 |
| H5: many index findings need no database | **Consistent but underpowered** as a comparison; the share is 56% on this benchmark and depends on its composition | section 6 |

## 8. Real-world validation (M6)

> **Not yet measured.** The 1,221 findings have not been labelled, so no real-world precision, kappa, false-positive causes or index-divergence rate exists. This section reports only what can be said without labels. Nothing below stands in for those numbers.

**Sample.** Repositories were chosen by a protocol written before searching and applied by code, without looking at what the analyzer finds. The pool of TypeScript repositories carrying the `prisma` topic had 2496 entries. Evaluated in a seeded random order, 104 were examined, 40 met all criteria, and the first 30 form the study set. The pool, and so the sample, is skewed towards small hobby and student projects.

**What the analyzer produced, without any judgement of correctness.** All 30 repositories were analyzed (0 failures) and produced 1221 findings. 8 repositories produced none.

| Rule | Findings |
|---|---|
| `MISSING_INDEX_ON_FILTERED_FIELD` | 154 |
| `MISSING_PAGINATION` | 720 |
| `N_PLUS_ONE_IN_LOOP` | 249 |
| `SEQUENTIAL_INDEPENDENT_AWAITS` | 49 |
| `UNBOUNDED_MUTATION` | 49 |

**Coverage gap (a result in its own right).** Zero findings does not mean clean code. In 5 repositories the analyzer located no Prisma operations at all, and in 4 of those a text search finds ten or more calls that look like Prisma operations:

| Repository | Source files loaded | Prisma operations the analyzer located | Text lookalike operations (heuristic) |
|---|---|---|---|
| Hereetria/shearcraft-booking | 177 | 0 | 74 |
| baiwumm/vue3-admin | 204 | 0 | 75 |
| erarbazansari/strikes-community | 142 | 0 | 52 |
| samwduncan/RowLab | 1168 | 0 | 0 |
| sixP-NaraKa/chatty | 87 | 0 | 30 |

The text count is a crude yardstick, not analysis. Causes seen in these projects: the client imported from a workspace package that cannot be resolved without installed dependencies; a NestJS service that extends `PrismaClient`; and a client wrapped in a factory and singleton. The cause in one repository was not identified. Dependencies were deliberately not installed, because installing runs code from untrusted repositories, so this measures the analyzer on source alone.

**What can and cannot be said.** Counting findings is not measuring precision. Until the findings are labelled, this chapter makes no claim about how many are correct, and no claim that the real-world numbers resemble the controlled ones.

## 9. Threats to validity

- **Synthetic, author-built test applications.** Two small applications with problems injected by the same person who built the analyzer, so the problem types match what the rules look for. The benchmark has 46 problems; the per-type results rest on two to six problems each, and interval widths reflect that.
- **Benchmark composition drives several numbers.** The H5 share, per-type recall, and the missed-by-everything types depend on what was injected.
- **Determinism removes repetition variance.** Ten repetitions demonstrate stability, not sampling variability of accuracy. Timing is measured on one machine with containers.
- **The A baseline cannot see the ORM.** A large A-to-C3 gap is partly a statement about that baseline. A-log reduces but does not remove this.
- **Ground truth was not edited after the fact**, including two apparent manifest omissions, so results describe the system and manifest as they were.
- **Sample size and selection in M6.** 30 repositories from a topic-based pool of small projects; one large well-known project. GitHub search is not exhaustive and the pool is enumerated with one truncated shard.
- **Labelling subjectivity in M6.** The author built the analyzer and is likely the first labeller; a second labeller covers at least 20% of every rule's findings for agreement, and disagreements are kept, not resolved.
- **Single ORM and database.** Prisma with PostgreSQL only; the abstraction for other ORMs and databases was not exercised.
- **Analyzer coverage on real code** (section 8): recall in the wild is unmeasured and evidently limited.

## 10. What this does and does not support

The results support one narrow claim: correlating evidence from several layers found more of the injected problems than any single layer, with few false positives, and the correlation exposes which layers support each finding. They also show that one plausible layer, runtime capture, added nothing here.

They do not support a claim that the framework beats existing tools (none was compared), that its precision on real projects is known (it is not yet measured), that the declared schema alone suffices in practice (the real-world divergence rate is unmeasured), or that the findings generalise beyond Prisma and PostgreSQL. The contribution is the correlation and its measurement, not a claim to have beaten existing tools.

## Appendix: where every number comes from

Generated with the chapter. Files are in `services/experiments/results/`; `results.json` is produced by `python -m experiments.analysis` and the others by `python -m experiments.writeup.collect`.

| Placeholder | Value as printed | Source |
|---|---|---|
| `cfg.C3.problems` | 46 | `results.json:configurations.C3.problem_bootstrap.problems` |
| `prov.repetitions` | 10 | `results.json:provenance.repetitions` |
| `prov.commit` | 4a2a347 | `results.json:provenance.git_commit` |
| `prov.sha` | 26a53e46f8be | `results.json:provenance.code_sha256` |
| `cfg.C3.detected` | 33 | `results.json:configurations.C3.pooled_over_apps.recall.mean x problems` |
| `cfg.C3.recall_ci` | 71.7% (95% CI 58.7% to 84.8%) | `results.json:configurations.C3.pooled_over_apps.recall.mean, results.json:configurations.C3.problem_bootstrap.recall` |
| `cfg.C3.precision_ci` | 94.3% (95% CI 85.7% to 100.0%) | `results.json:configurations.C3.pooled_over_apps.precision.mean, results.json:configurations.C3.problem_bootstrap.precision` |
| `cfg.C3.f1_ci` | 81.5% (95% CI 71.5% to 89.3%) | `results.json:configurations.C3.pooled_over_apps.f1.mean, results.json:configurations.C3.problem_bootstrap.f1` |
| `cfg.C3.fpr` | 0.5% | `results.json:configurations.C3.pooled_over_apps.false_positive_rate.mean` |
| `cfg.C3.fp` | 2 | `results.json:configurations.C3: scored_findings - detected` |
| `cfg.C3.scored` | 35 | `results.json:configurations.C3.problem_bootstrap.scored_findings` |
| `block:accuracy_table` | (table) | `results.json:configurations.*.pooled_over_apps.{precision,recall,f1,false_positive_rate}, problem_bootstrap.*` |
| `block:type_table` | (table) | `results.json:configurations.*.per_problem_type.*.{entries,recall.mean}` |
| `typ.C3.missing_index.tp` | 5 | `results.json:configurations.C3.per_problem_type.missing_index.tp.mean` |
| `typ.C3.missing_index.entries` | 6 | `results.json:configurations.C3.per_problem_type.missing_index.entries` |
| `typ.C3.excessive_relation_loading.entries` | 6 | `results.json:configurations.C3.per_problem_type.excessive_relation_loading.entries` |
| `typ.C3.repeated_identical_query.entries` | 6 | `results.json:configurations.C3.per_problem_type.repeated_identical_query.entries` |
| `typ.C3.excessive_relation_loading.recall` | 0% | `results.json:configurations.C3.per_problem_type.excessive_relation_loading.recall.mean` |
| `typ.C3.repeated_identical_query.recall` | 0% | `results.json:configurations.C3.per_problem_type.repeated_identical_query.recall.mean` |
| `typ.C3.missing_index.recall` | 83.3% | `results.json:configurations.C3.per_problem_type.missing_index.recall.mean` |
| `typ.C3.duplicate_spike.fp` | 2 | `results.json:configurations.C3.per_problem_type.duplicate_spike.fp.mean` |
| `typ.C3.duplicate_spike.precision` | 60% | `results.json:configurations.C3.per_problem_type.duplicate_spike.precision.mean` |
| `cfg.A.detected` | 0 | `results.json:configurations.A.pooled_over_apps.recall.mean x problems` |
| `cfg.A.problems` | 46 | `results.json:configurations.A.problem_bootstrap.problems` |
| `cfg.B1.detected` | 12 | `results.json:configurations.B1.pooled_over_apps.recall.mean x problems` |
| `cfg.B1.precision` | 100% | `results.json:configurations.B1.pooled_over_apps.precision.mean` |
| `cfg.B1.recall_ci` | 26.1% (95% CI 13.0% to 39.1%) | `results.json:configurations.B1.pooled_over_apps.recall.mean, results.json:configurations.B1.problem_bootstrap.recall` |
| `cmp.H2_A_vs_B1.only_second` | 12 | `results.json:comparisons[H2_A_vs_B1].detection_mcnemar_exact.only_second` |
| `cmp.H2_A_vs_B1.only_first` | 0 | `results.json:comparisons[H2_A_vs_B1].detection_mcnemar_exact.only_first` |
| `cmp.H2_A_vs_B1.p` | 4.9e-04 | `results.json:comparisons[H2_A_vs_B1].detection_mcnemar_exact.p_value` |
| `cmp.H2_A_vs_B1.recall_diff` | 26.1% (95% CI 13.0% to 39.1%) | `results.json:comparisons[H2_A_vs_B1].accuracy_difference_bootstrap.recall` |
| `cfg.A-log.detected` | 6 | `results.json:configurations.A-log.pooled_over_apps.recall.mean x problems` |
| `cfg.A-log.precision` | 21% | `results.json:configurations.A-log.pooled_over_apps.precision.mean` |
| `cmp.S_Alog_vs_C3.only_second` | 27 | `results.json:comparisons[S_Alog_vs_C3].detection_mcnemar_exact.only_second` |
| `cmp.S_Alog_vs_C3.only_first` | 0 | `results.json:comparisons[S_Alog_vs_C3].detection_mcnemar_exact.only_first` |
| `cmp.S_Alog_vs_C3.recall_diff` | 58.7% (95% CI 43.5% to 71.7%) | `results.json:comparisons[S_Alog_vs_C3].accuracy_difference_bootstrap.recall` |
| `cmp.H3_C1_vs_C2.only_second` | 0 | `results.json:comparisons[H3_C1_vs_C2].detection_mcnemar_exact.only_second` |
| `cmp.H3_C1_vs_C2.only_first` | 0 | `results.json:comparisons[H3_C1_vs_C2].detection_mcnemar_exact.only_first` |
| `cfg.C1.recall` | 45.7% | `results.json:configurations.C1.pooled_over_apps.recall.mean` |
| `cfg.C1.precision` | 100% | `results.json:configurations.C1.pooled_over_apps.precision.mean` |
| `cmp.H3_C1_vs_C2.p` | 1.000 | `results.json:comparisons[H3_C1_vs_C2].detection_mcnemar_exact.p_value` |
| `cmp.H3_C1_vs_C2.conf_n` | 21 | `results.json:comparisons[H3_C1_vs_C2].confidence_wilcoxon.n` |
| `cmp.H3_C1_vs_C2.conf_first` | 2.86 | `results.json:comparisons[H3_C1_vs_C2].confidence_wilcoxon.first_mean` |
| `cmp.H3_C1_vs_C2.conf_second` | 2.86 | `results.json:comparisons[H3_C1_vs_C2].confidence_wilcoxon.second_mean` |
| `cmp.H3_C1_vs_C2.conf_p` | 1.000 | `results.json:comparisons[H3_C1_vs_C2].confidence_wilcoxon.p_value` |
| `cmp.H3_C1_vs_C2.cpu_first` | 2.22 | `results.json:comparisons[H3_C1_vs_C2].timing_wilcoxon.cpu_s.first_mean` |
| `cmp.H3_C1_vs_C2.cpu_second` | 2.36 | `results.json:comparisons[H3_C1_vs_C2].timing_wilcoxon.cpu_s.second_mean` |
| `cmp.H3_C1_vs_C2.cpu_p` | 5.7e-06 | `results.json:comparisons[H3_C1_vs_C2].timing_wilcoxon.cpu_s.p_value` |
| `cmp.H3_C1_vs_C2.cpu_cliffs` | 0.70 | `results.json:comparisons[H3_C1_vs_C2].timing_wilcoxon.cpu_s.cliffs_delta` |
| `cfg.C1.wall_s` | 2.5 | `results.json:configurations.C1.pooled_over_apps.wall_s.mean` |
| `cfg.C2.wall_s` | 9.8 | `results.json:configurations.C2.pooled_over_apps.wall_s.mean` |
| `cfg.C2.recall` | 45.7% | `results.json:configurations.C2.pooled_over_apps.recall.mean` |
| `cfg.C3.recall` | 71.7% | `results.json:configurations.C3.pooled_over_apps.recall.mean` |
| `typ.C3.null_spike.recall` | 100% | `results.json:configurations.C3.per_problem_type.null_spike.recall.mean` |
| `typ.C3.distribution_shift.recall` | 100% | `results.json:configurations.C3.per_problem_type.distribution_shift.recall.mean` |
| `typ.C3.duplicate_spike.recall` | 100% | `results.json:configurations.C3.per_problem_type.duplicate_spike.recall.mean` |
| `typ.C3.null_spike.entries` | 3 | `results.json:configurations.C3.per_problem_type.null_spike.entries` |
| `typ.C3.distribution_shift.entries` | 3 | `results.json:configurations.C3.per_problem_type.distribution_shift.entries` |
| `typ.C3.duplicate_spike.entries` | 3 | `results.json:configurations.C3.per_problem_type.duplicate_spike.entries` |
| `bt.alarms` | 5 | `anomaly_backtest_*.json: sum of vote_result.alarms_above` |
| `bt.evaluations` | 515 | `anomaly_backtest_*.json: sum of vote_result.evaluations` |
| `bt.rate` | 1.0% | `alarms / evaluations` |
| `bt.ecommerce.alarms` | 3 | `anomaly_backtest_ecommerce.json:vote_result.alarms_above` |
| `bt.ecommerce.evaluations` | 294 | `anomaly_backtest_ecommerce.json:vote_result.evaluations` |
| `bt.blog.alarms` | 2 | `anomaly_backtest_blog.json:vote_result.alarms_above` |
| `bt.blog.evaluations` | 221 | `anomaly_backtest_blog.json:vote_result.evaluations` |
| `bt.detector.zscore` | 5 | `anomaly_backtest_*.json: sum of per_detector.zscore.alarms_above` |
| `bt.detector.iqr` | 13 | `anomaly_backtest_*.json: sum of per_detector.iqr.alarms_above` |
| `bt.detector.moving_average` | 4 | `anomaly_backtest_*.json: sum of per_detector.moving_average.alarms_above` |
| `block:cost_table` | (table) | `results.json:configurations.*.pooled_over_apps.{detection_latency_s,cpu_s,wall_s}` |
| `cfg.C2.fpr` | 0.00% | `results.json:configurations.C2.pooled_over_apps.false_positive_rate.mean` |
| `cfg.A-log.fpr` | 6.3% | `results.json:configurations.A-log.pooled_over_apps.false_positive_rate.mean` |
| `cfg.C3.cpu_s` | 4.82 | `results.json:configurations.C3.pooled_over_apps.cpu_s.mean` |
| `cfg.B2.cpu_s` | 4.39 | `results.json:configurations.B2.pooled_over_apps.cpu_s.mean` |
| `cfg.A.cpu_s` | 0.013 | `results.json:configurations.A.pooled_over_apps.cpu_s.mean` |
| `oh.sessions` | 5 | `collector_overhead.json:sessions` |
| `block:overhead_table` | (table) | `collector_overhead.json:sessions[*]` |
| `oh.ecommerce.ms_min` | 0.38 | `collector_overhead.json: ecommerce sessions` |
| `oh.ecommerce.ms_max` | 0.57 | `collector_overhead.json: ecommerce sessions` |
| `oh.ecommerce.ratio_min` | 9.8% | `collector_overhead.json: ecommerce sessions` |
| `oh.ecommerce.ratio_max` | 16.4% | `collector_overhead.json: ecommerce sessions` |
| `oh.blog.ms_min` | 0.18 | `collector_overhead.json: blog sessions` |
| `oh.blog.ms_max` | 0.26 | `collector_overhead.json: blog sessions` |
| `oh.blog.ratio_min` | 4.6% | `collector_overhead.json: blog sessions` |
| `oh.blog.ratio_max` | 7.3% | `collector_overhead.json: blog sessions` |
| `cmp.RQ6_B2_vs_C1.only_second` | 4 | `results.json:comparisons[RQ6_B2_vs_C1].detection_mcnemar_exact.only_second` |
| `cmp.RQ6_B2_vs_C1.only_first` | 0 | `results.json:comparisons[RQ6_B2_vs_C1].detection_mcnemar_exact.only_first` |
| `cmp.RQ6_B2_vs_C1.recall_diff` | 8.7% (95% CI 2.2% to 17.4%) | `results.json:comparisons[RQ6_B2_vs_C1].accuracy_difference_bootstrap.recall` |
| `cmp.RQ6_B2_vs_C1.p` | 0.125 | `results.json:comparisons[RQ6_B2_vs_C1].detection_mcnemar_exact.p_value` |
| `cmp.RQ6_B2_vs_C1.p_holm` | 0.250 | `results.json:comparisons[RQ6_B2_vs_C1].detection_p_holm` |
| `cmp.H5_B1_vs_B2.only_second` | 5 | `results.json:comparisons[H5_B1_vs_B2].detection_mcnemar_exact.only_second` |
| `cmp.H5_B1_vs_B2.only_first` | 0 | `results.json:comparisons[H5_B1_vs_B2].detection_mcnemar_exact.only_first` |
| `cmp.H5_B1_vs_B2.recall_diff` | 10.9% (95% CI 2.2% to 21.7%) | `results.json:comparisons[H5_B1_vs_B2].accuracy_difference_bootstrap.recall` |
| `cmp.H5_B1_vs_B2.p` | 0.062 | `results.json:comparisons[H5_B1_vs_B2].detection_mcnemar_exact.p_value` |
| `cmp.H5_B1_vs_B2.p_holm` | 0.188 | `results.json:comparisons[H5_B1_vs_B2].detection_p_holm` |
| `h5.obtainable` | 9 | `results.json:h5_index_share.obtainable_with_database` |
| `h5.also` | 5 | `results.json:h5_index_share.also_from_declared_schema_alone` |
| `h5.share_ci` | 55.6% (95% CI 26.7% to 81.1%) | `results.json:h5_index_share.share, results.json:h5_index_share.wilson_95` |
| `h5.missing_index.also_from_declared_schema_alone` | 5 | `results.json:h5_index_share.per_type.missing_index.also_from_declared_schema_alone` |
| `h5.missing_index.obtainable_with_database` | 5 | `results.json:h5_index_share.per_type.missing_index.obtainable_with_database` |
| `h5.index_not_declared.also_from_declared_schema_alone` | 0 | `results.json:h5_index_share.per_type.index_not_declared.also_from_declared_schema_alone` |
| `h5.index_not_declared.obtainable_with_database` | 2 | `results.json:h5_index_share.per_type.index_not_declared.obtainable_with_database` |
| `h5.declared_index_not_applied.also_from_declared_schema_alone` | 0 | `results.json:h5_index_share.per_type.declared_index_not_applied.also_from_declared_schema_alone` |
| `h5.declared_index_not_applied.obtainable_with_database` | 2 | `results.json:h5_index_share.per_type.declared_index_not_applied.obtainable_with_database` |
| `cfg.B2.precision` | 100% | `results.json:configurations.B2.pooled_over_apps.precision.mean` |
| `cmp.H1_A_vs_C3.only_second` | 33 | `results.json:comparisons[H1_A_vs_C3].detection_mcnemar_exact.only_second` |
| `cmp.H1_A_vs_C3.only_first` | 0 | `results.json:comparisons[H1_A_vs_C3].detection_mcnemar_exact.only_first` |
| `cmp.H1_A_vs_C3.p_holm` | 9.3e-10 | `results.json:comparisons[H1_A_vs_C3].detection_p_holm` |
| `h5.share` | 56% | `results.json:h5_index_share.share` |
| `block:labels` | (table) | `labels_results.json does not exist` |
| `rw.pool_size` | 2496 | `realworld_summary.json:pool_size` |
| `rw.evaluated` | 104 | `realworld_summary.json:evaluated` |
| `rw.eligible` | 40 | `realworld_summary.json:eligible` |
| `rw.study_repositories` | 30 | `realworld_summary.json:study_repositories` |
| `rw.repositories_analyzed_ok` | 30 | `realworld_summary.json:repositories_analyzed_ok` |
| `rw.repositories_failed` | 0 | `realworld_summary.json:repositories_failed` |
| `rw.findings` | 1221 | `realworld_summary.json:findings` |
| `rw.repositories_with_zero_findings` | 8 | `realworld_summary.json:repositories_with_zero_findings` |
| `block:realworld_rules` | (table) | `realworld_summary.json:findings_by_rule` |
| `cov.zero` | 5 | `realworld_coverage.json:with_zero_located_operations` |
| `cov.zero_lookalikes` | 4 | `realworld_coverage.json:zero_located_but_text_lookalikes_ge_10` |
| `block:coverage_table` | (table) | `realworld_coverage.json:repositories[with zero located operations]` |
