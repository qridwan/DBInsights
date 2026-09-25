import { prisma } from "./db";

// Every Prisma call below is inside a loop over the result of an earlier
// Prisma call. iteratesOverORMResult must be true, with sourceOperationLine
// pointing at the originating call (marked `// source`).

export async function forOfAwaitedVariable() {
  const users = await prisma.user.findMany({ take: 10 }); // source
  for (const user of users) {
    await prisma.task.count({ where: { assigneeId: user.id } });
  }
}

export async function chainedMap() {
  return Promise.all(
    (await prisma.user.findMany({ take: 10 })).map((user) => prisma.task.count({ where: { assigneeId: user.id } })), // source
  );
}

export async function chainedForEach() {
  (await prisma.project.findMany({ take: 10 })).forEach((project) => { // source
    void prisma.task.count({ where: { projectId: project.id } });
  });
}

export async function mapOverVariable() {
  const projects = await prisma.project.findMany({ take: 10 }); // source
  return Promise.all(projects.map((project) => prisma.task.findMany({ where: { projectId: project.id }, take: 5 })));
}

export async function intermediateAssignment() {
  const users = await prisma.user.findMany({ take: 10 }); // source
  const selected = users;
  for (const user of selected) {
    await prisma.task.count({ where: { assigneeId: user.id } });
  }
}

export async function intermediateFilter() {
  const users = await prisma.user.findMany({ take: 10 }); // source
  const active = users.filter((user) => user.active);
  for (const user of active) {
    await prisma.task.count({ where: { assigneeId: user.id } });
  }
}

export async function awaitedLater() {
  const pending = prisma.user.findMany({ take: 10 }); // source
  const users = await pending;
  for (const user of users) {
    await prisma.task.count({ where: { assigneeId: user.id } });
  }
}

export async function destructuredPromiseAll() {
  const [teams, projects] = await Promise.all([
    prisma.team.findMany({ take: 10 }),
    prisma.project.findMany({ take: 10 }), // source
  ]);
  for (const project of projects) {
    await prisma.task.count({ where: { projectId: project.id } });
  }
  return teams;
}

export async function nestedRelationList() {
  const projects = await prisma.project.findMany({ take: 10, include: { tasks: true } }); // source
  for (const project of projects) {
    for (const task of project.tasks) {
      await prisma.user.findUnique({ where: { id: task.assigneeId ?? 0 } });
    }
  }
}
