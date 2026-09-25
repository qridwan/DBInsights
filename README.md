# DBInsight

DBInsight is a hybrid static and runtime analysis framework that detects database performance and data-quality problems in Prisma/PostgreSQL applications. Its TypeScript core analyzes application source and the declared `schema.prisma` without a database connection, while Python services add SQL analysis, runtime query statistics, and data-quality profiling. It is the research implementation for PMIT-6000 at IIT, Jahangirnagar University.
