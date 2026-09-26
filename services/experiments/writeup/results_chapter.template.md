# Results

*Draft generated from stored results. Every number is looked up, not typed; see the appendix.*

## 0. How to read this chapter

Two kinds of evidence are reported and are **never combined into one claim**.

- **Controlled experiment (M5).** Two test applications with {{cfg.C3.problems}} problems injected by the author and recorded in a ground-truth manifest. Each of seven configurations was run {{prov.repetitions}} times per application. It measures what each evidence layer contributes when the answer is known.
- **Real-world validation (M6).** Open-source projects the author did not write, with no known answer. It measures precision only, and only after human labelling (section 8).

Two properties of the controlled experiment shape every number below.

1. **Accuracy is deterministic.** For a fixed database, source tree and manifest, a configuration finds the same problems on every repetition. Repetitions therefore add no variance to accuracy; they show that it is stable and are informative only for timing. Accuracy uncertainty comes from the finite set of {{cfg.C3.problems}} problems, so accuracy intervals are bootstrap intervals over problems, and paired comparisons are exact McNemar tests on per-problem outcomes.
2. **The problems were injected by the author, who also built the analyzer.** The injected types mirror what the rules look for. Results show that each layer finds what it was designed to find; they are not an estimate of how common these problems are anywhere.

The experiment ran on code with uncommitted changes (commit `{{prov.commit}}`, working-tree hash `{{prov.sha}}`), recorded so the result can be tied to the exact code.

## 1. RQ1: how effectively does the hybrid framework detect problems?

Configuration **C3** enables every layer: static ORM analysis, SQL analysis, the declared schema, the actual schema, runtime capture and data-quality statistics. Pooled over both applications it found {{cfg.C3.detected}} of {{cfg.C3.problems}} problems.

- Recall: {{cfg.C3.recall_ci|ci}}
- Precision: {{cfg.C3.precision_ci|ci}}
- F1: {{cfg.C3.f1_ci|ci}}
- False-positive rate: {{cfg.C3.fpr|pct1}}, with {{cfg.C3.fp}} false positives among {{cfg.C3.scored}} scored findings.

{{block:accuracy_table}}

Intervals are 95% bootstrap intervals over the benchmark's problems.

**By problem type** (recall, mean over repetitions):

{{block:type_table}}

**What the result says.** The hybrid finds most of what was injected, with few false positives. It finds every problem of eight of the eleven problem types, and {{typ.C3.missing_index.tp|int}} of {{typ.C3.missing_index.entries}} of a ninth. The data-quality types are found only once the data layer is on (the step from C2 to C3).

**What it does not say.**
- **Two problem types are missed by every configuration.** `excessive_relation_loading` and `repeated_identical_query` have {{typ.C3.excessive_relation_loading.entries}} and {{typ.C3.repeated_identical_query.entries}} problems each, and recall is {{typ.C3.excessive_relation_loading.recall|pct0}} and {{typ.C3.repeated_identical_query.recall|pct0}} in C3. The system has no rule for them, so this is a coverage gap, not a near miss.
- One `missing_index` problem is missed by every configuration that has the ORM layer ({{typ.C3.missing_index.recall|pct1}} recall). This is a known limitation of the analyzer's handling of a shorthand `{ where }` filter, left unfixed on purpose so the results describe the system as built.
- **Precision below 100% comes from one type.** `duplicate_spike` has {{typ.C3.duplicate_spike.fp|int}} false positives (precision {{typ.C3.duplicate_spike.precision|pct0}}). Both are duplicate-rate findings on the `Post` table, in columns the manifest does not label. Whether they are real side effects of the injection that the manifest failed to record was not adjudicated; the manifest was not edited after the results were seen, so both count as false positives.
- **This is a comparison with layers of the same system, not with existing tools.** No other tool was run.

## 2. RQ2: does ORM-aware source analysis find problems that SQL analysis alone misses?

Two configurations answer this. **A** is static SQL analysis alone, over the SQL text in the repository. **B1** adds ORM-aware source analysis.

- A found {{cfg.A.detected}} of {{cfg.A.problems}} problems. B1 found {{cfg.B1.detected}}, with precision {{cfg.B1.precision|pct0}} and recall {{cfg.B1.recall_ci|ci}}.
- Paired on the same problems, B1 found {{cmp.H2_A_vs_B1.only_second}} that A missed and A found {{cmp.H2_A_vs_B1.only_first}} that B1 missed (exact McNemar p = {{cmp.H2_A_vs_B1.p|p}}, not part of the corrected family; recall difference {{cmp.H2_A_vs_B1.recall_diff|ci}}).

**What the result says.** On these Prisma applications, N+1 patterns and unpaginated queries are visible in source through the ORM's API and are not visible as SQL text.

**What it does not say.** The comparison is close to definitional. Prisma builds its SQL at run time, so SQL analysis of the repository finds almost nothing to analyse; A finding zero problems says more about the baseline's input than about SQL analysis as a technique. To avoid a strawman baseline a sensitivity arm, **A-log**, gives the SQL analyzer the statements the application actually issued (as a query log would). A-log found {{cfg.A-log.detected}} problems with precision {{cfg.A-log.precision|pct0}}. The hybrid C3 still found {{cmp.S_Alog_vs_C3.only_second}} problems that A-log missed and lost {{cmp.S_Alog_vs_C3.only_first}} (recall difference {{cmp.S_Alog_vs_C3.recall_diff|ci}}). A-log is an addition to the plan and is reported separately from the six configurations.

## 3. RQ3: does combining static analysis with runtime behaviour improve precision and recall?

This is the C1 to C2 step: runtime capture added to everything else.

- Problems gained by runtime: **{{cmp.H3_C1_vs_C2.only_second}}**, lost: **{{cmp.H3_C1_vs_C2.only_first}}**. Precision and recall are identical ({{cfg.C1.recall|pct1}} recall and {{cfg.C1.precision|pct0}} precision in both), exact McNemar p = {{cmp.H3_C1_vs_C2.p|p}}.
- Confidence of the matching finding, over the {{cmp.H3_C1_vs_C2.conf_n}} problems both found: mean {{cmp.H3_C1_vs_C2.conf_first|f2}} without runtime, {{cmp.H3_C1_vs_C2.conf_second|f2}} with it (scale 1 to 3), Wilcoxon p = {{cmp.H3_C1_vs_C2.conf_p|p}}.
- Cost: {{cmp.H3_C1_vs_C2.cpu_first|f2}} s to {{cmp.H3_C1_vs_C2.cpu_second|f2}} s CPU per application run (Wilcoxon p = {{cmp.H3_C1_vs_C2.cpu_p|p}}, Cliff's delta {{cmp.H3_C1_vs_C2.cpu_cliffs|f2}}). Wall time rises from {{cfg.C1.wall_s|f1}} s to {{cfg.C2.wall_s|f1}} s, because runtime capture drives real traffic.

**This result contradicts hypothesis H3** ("runtime analysis provides stronger evidence for performance findings than static analysis alone"). In this experiment runtime evidence added no detections and no confidence, and cost time.

**Why, and what this does not show.** The runtime layer has a single rule, runtime N+1 detection. It fires on the problems that static analysis already finds, so it corroborates rather than adds. The two problem types only runtime behaviour could reveal have no runtime rule (RQ1). The result therefore does not show that runtime evidence cannot help; it shows that, with one runtime rule and problems that are also statically visible, it did not help here. Runtime findings do appear in the evidence chain of the findings they corroborate (the dashboard shows this chain for each finding), which is a qualitative benefit the recall and confidence measures do not capture.

## 4. RQ4: can statistical anomaly detection identify unexpected changes?

**Data characteristics.** Three detectors (z-score, IQR, moving average) learn an expected range for each column's null rate, duplicate rate and value distribution from that column's own history, and a majority vote flags a window. Adding the data layer (C2 to C3) raised recall from {{cfg.C2.recall|pct1}} to {{cfg.C3.recall|pct1}}. Every injected `null_spike`, `distribution_shift` and `duplicate_spike` problem was found (recall {{typ.C3.null_spike.recall|pct0}}, {{typ.C3.distribution_shift.recall|pct0}} and {{typ.C3.duplicate_spike.recall|pct0}}, on {{typ.C3.null_spike.entries}}, {{typ.C3.distribution_shift.entries}} and {{typ.C3.duplicate_spike.entries}} problems), at the price of the {{typ.C3.duplicate_spike.fp|int}} duplicate-rate false positives above.

**False alarms on clean history.** Walking forward over history known to be clean, each window judged only against earlier ones, the majority vote raised {{bt.alarms}} increase alarms in {{bt.evaluations}} evaluations ({{bt.rate|pct1}}): {{bt.ecommerce.alarms}} of {{bt.ecommerce.evaluations}} on the e-commerce application and {{bt.blog.alarms}} of {{bt.blog.evaluations}} on the blog. Individually the detectors raised {{bt.detector.zscore}} (z-score), {{bt.detector.iqr}} (IQR) and {{bt.detector.moving_average}} (moving average) increase alarms, so the IQR detector is the noisiest and the vote suppresses part of that.

**What the result says.** Learned, per-column ranges detected all injected data-quality changes without a fixed threshold, at a low false-alarm rate on clean history.

**What it does not say.**
- **RQ4 also asks about query behaviour, and that half is not measured.** No statistical detector runs over query behaviour. Runtime N+1 detection is rule-based, not statistical.
- The injected changes are large (a null rate moved from a few percent to over half, a distribution moved by tens of points). Sensitivity to small changes was not measured.
- The clean history is 12 synthetic windows of 30 days from a deterministic seed, which is more regular than production data.

## 5. RQ5: what trade-offs exist between accuracy, false positives and overhead?

{{block:cost_table}}

Intervals are 95% t-intervals over repetitions; time to first detection is the mean over detected problems, in seconds from the start of the run.

- **False positives.** The ablation configurations up to C2 have a false-positive rate of {{cfg.C2.fpr|pct2}}; C3 has {{cfg.C3.fpr|pct2}}. Adding the data layer raised recall from {{cfg.C2.recall|pct1}} to {{cfg.C3.recall|pct1}} and introduced every false positive among the six ablation configurations. The sensitivity arm A-log has a higher rate ({{cfg.A-log.fpr|pct1}}), because it judges SQL text without the schema or source context.
- **Analysis cost.** C3 uses {{cfg.C3.cpu_s|f2}} s CPU per run against {{cfg.B2.cpu_s|f2}} s for B2, which needs no database, and {{cfg.A.cpu_s|f3}} s for A, which finds nothing.
- **Runtime cost without a return.** The step to C2 adds cost and no accuracy (RQ3).

**Collector overhead.** The runtime collector was switched on and off in ABBA order. Every stored session with at least ten repetitions is reported, because the measured overhead varies between sessions and no single session should stand for the rest ({{oh.sessions}} sessions):

{{block:overhead_table}}

Across sessions the median added latency per request was {{oh.ecommerce.ms_min|f2}} to {{oh.ecommerce.ms_max|f2}} ms on the e-commerce application ({{oh.ecommerce.ratio_min|pct1}} to {{oh.ecommerce.ratio_max|pct1}} of median latency) and {{oh.blog.ms_min|f2}} to {{oh.blog.ms_max|f2}} ms on the blog ({{oh.blog.ratio_min|pct1}} to {{oh.blog.ratio_max|pct1}}).

**What the result says.** The collector adds a fraction of a millisecond to a median request of about four milliseconds.

**What it does not say.** The requests are tiny, from a fixed local load script against a local database; the overhead ratio would look different for slower queries. The applications are small. Several sessions came from different code states, which is part of why the range is reported.

## 6. RQ6: how far does the declared schema diverge from the actual one?

The declared schema (`schema.prisma`) and the actual schema (the live database catalog) are separate evidence sources and were never merged. Four divergences were injected, two in each direction: an index in the database that the schema does not declare (`index_not_declared`), and an index the schema declares that the database lacks (`declared_index_not_applied`).

- **What the live database adds (B2 to C1).** C1 found {{cmp.RQ6_B2_vs_C1.only_second}} problems B2 missed and lost {{cmp.RQ6_B2_vs_C1.only_first}} (recall difference {{cmp.RQ6_B2_vs_C1.recall_diff|ci}}). The exact test gives p = {{cmp.RQ6_B2_vs_C1.p|p}} (Holm-corrected {{cmp.RQ6_B2_vs_C1.p_holm|p}}), **not significant**. The exact test cannot go below p = 0.0625 with only four discordant problems, so the test has too little power to declare significance whatever the effect; the direction is consistent (all four in C1's favour) and the interval excludes zero.
- **What the declared schema adds (B1 to B2, hypothesis H5's comparison).** B2 found {{cmp.H5_B1_vs_B2.only_second}} problems B1 missed and lost {{cmp.H5_B1_vs_B2.only_first}} (recall difference {{cmp.H5_B1_vs_B2.recall_diff|ci}}); exact p = {{cmp.H5_B1_vs_B2.p|p}}, Holm-corrected {{cmp.H5_B1_vs_B2.p_holm|p}}, **not significant** for the same reason. All five are `missing_index` problems, which need the declared schema to judge.
- **Hypothesis H5 stated directly.** H5 claims that a substantial share of the index findings obtainable from the live database are also obtainable from the declared schema alone. Of the {{h5.obtainable}} index problems obtainable with the database, {{h5.also}} were also obtainable from source and the declared schema alone: **{{h5.share_ci|ci}}** (Wilson interval). By type: {{h5.missing_index.also_from_declared_schema_alone}} of {{h5.missing_index.obtainable_with_database}} `missing_index`, {{h5.index_not_declared.also_from_declared_schema_alone}} of {{h5.index_not_declared.obtainable_with_database}} `index_not_declared`, {{h5.declared_index_not_applied.also_from_declared_schema_alone}} of {{h5.declared_index_not_applied.obtainable_with_database}} `declared_index_not_applied`.

**What the result says.** A database connection adds exactly the divergence findings: the declared schema alone cannot see an index that is only in the database, or only in the schema file. The declared schema by itself carries the missing-index findings that need no database.

**What it does not say.**
- **The H5 share is a property of the benchmark, not of the world.** The denominator was fixed by how many problems of each kind were injected; with more divergence instances the share would be lower, with fewer it would be higher. It is not an estimate of how often real projects diverge. The real-world divergence rate is the quantity that would answer RQ6, and it has not been measured (section 8).
- **The cost of divergence to declared-only findings was not observed.** In the controlled applications no declared-only finding was a false positive because of divergence (B2 precision {{cfg.B2.precision|pct0}}).
- Two instances per divergence direction is a small number.

## 7. The hypotheses at a glance

| Hypothesis | Result | Where |
|---|---|---|
| H1: hybrid detects a broader range than SQL alone | **Supported.** C3 found {{cmp.H1_A_vs_C3.only_second}} problems A missed, lost {{cmp.H1_A_vs_C3.only_first}} (Holm p = {{cmp.H1_A_vs_C3.p_holm|p}}). Against the stronger A-log baseline it still held ({{cmp.S_Alog_vs_C3.only_second}} gained, {{cmp.S_Alog_vs_C3.only_first}} lost) | section 2 |
| H2: ORM-aware analysis improves anti-pattern detection | **Supported** on N+1 and unpaginated queries ({{cmp.H2_A_vs_B1.only_second}} gained), with the caveat that the baseline cannot see the ORM | section 2 |
| H3: runtime gives stronger evidence than static alone | **Contradicted.** {{cmp.H3_C1_vs_C2.only_second}} gained, no change in confidence, extra cost | section 3 |
| H4: anomaly detection finds meaningful changes | **Supported for data characteristics**; not tested for query behaviour | section 4 |
| H5: many index findings need no database | **Consistent but underpowered** as a comparison; the share is {{h5.share|pct0}} on this benchmark and depends on its composition | section 6 |

## 8. Real-world validation (M6)

{{block:labels}}

**Sample.** Repositories were chosen by a protocol written before searching and applied by code, without looking at what the analyzer finds. The pool of TypeScript repositories carrying the `prisma` topic had {{rw.pool_size}} entries. Evaluated in a seeded random order, {{rw.evaluated}} were examined, {{rw.eligible}} met all criteria, and the first {{rw.study_repositories}} form the study set. The pool, and so the sample, is skewed towards small hobby and student projects.

**What the analyzer produced, without any judgement of correctness.** All {{rw.repositories_analyzed_ok}} repositories were analyzed ({{rw.repositories_failed}} failures) and produced {{rw.findings}} findings. {{rw.repositories_with_zero_findings}} repositories produced none.

{{block:realworld_rules}}

**Coverage gap (a result in its own right).** Zero findings does not mean clean code. In {{cov.zero}} repositories the analyzer located no Prisma operations at all, and in {{cov.zero_lookalikes}} of those a text search finds ten or more calls that look like Prisma operations:

{{block:coverage_table}}

The text count is a crude yardstick, not analysis. Causes seen in these projects: the client imported from a workspace package that cannot be resolved without installed dependencies; a NestJS service that extends `PrismaClient`; and a client wrapped in a factory and singleton. The cause in one repository was not identified. Dependencies were deliberately not installed, because installing runs code from untrusted repositories, so this measures the analyzer on source alone.

**What can and cannot be said.** Counting findings is not measuring precision. Until the findings are labelled, this chapter makes no claim about how many are correct, and no claim that the real-world numbers resemble the controlled ones.

## 9. Threats to validity

- **Synthetic, author-built test applications.** Two small applications with problems injected by the same person who built the analyzer, so the problem types match what the rules look for. The benchmark has {{cfg.C3.problems}} problems; the per-type results rest on two to six problems each, and interval widths reflect that.
- **Benchmark composition drives several numbers.** The H5 share, per-type recall, and the missed-by-everything types depend on what was injected.
- **Determinism removes repetition variance.** Ten repetitions demonstrate stability, not sampling variability of accuracy. Timing is measured on one machine with containers.
- **The A baseline cannot see the ORM.** A large A-to-C3 gap is partly a statement about that baseline. A-log reduces but does not remove this.
- **Ground truth was not edited after the fact**, including two apparent manifest omissions, so results describe the system and manifest as they were.
- **Sample size and selection in M6.** {{rw.study_repositories}} repositories from a topic-based pool of small projects; one large well-known project. GitHub search is not exhaustive and the pool is enumerated with one truncated shard.
- **Labelling subjectivity in M6.** The author built the analyzer and is likely the first labeller; a second labeller covers at least 20% of every rule's findings for agreement, and disagreements are kept, not resolved.
- **Single ORM and database.** Prisma with PostgreSQL only; the abstraction for other ORMs and databases was not exercised.
- **Analyzer coverage on real code** (section 8): recall in the wild is unmeasured and evidently limited.

## 10. What this does and does not support

The results support one narrow claim: correlating evidence from several layers found more of the injected problems than any single layer, with few false positives, and the correlation exposes which layers support each finding. They also show that one plausible layer, runtime capture, added nothing here.

They do not support a claim that the framework beats existing tools (none was compared), that its precision on real projects is known (it is not yet measured), that the declared schema alone suffices in practice (the real-world divergence rate is unmeasured), or that the findings generalise beyond Prisma and PostgreSQL. The contribution is the correlation and its measurement, not a claim to have beaten existing tools.
