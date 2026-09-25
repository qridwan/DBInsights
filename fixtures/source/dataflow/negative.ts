import { prisma } from "./db";

// Every Prisma call below sits inside a loop whose iterable does NOT come from
// an earlier Prisma call. iteratesOverORMResult must be false for all of them.

export async function literalArrayInline() {
  for (const id of [1, 2, 3]) {
    await prisma.user.findUnique({ where: { id } });
  }
}

export async function literalArrayConst() {
  const ids = [1, 2, 3];
  for (const id of ids) {
    await prisma.user.findUnique({ where: { id } });
  }
}

export async function literalArrayMap() {
  return Promise.all([1, 2, 3].map((id) => prisma.user.findUnique({ where: { id } })));
}

export async function parameterOfUnknownOrigin(ids: number[]) {
  for (const id of ids) {
    await prisma.user.findUnique({ where: { id } });
  }
}

export async function parameterMap(ids: number[]) {
  return Promise.all(ids.map((id) => prisma.task.count({ where: { assigneeId: id } })));
}

export async function fetchResults(url: string) {
  const response = await fetch(url);
  const items: { id: number }[] = await response.json();
  for (const item of items) {
    await prisma.user.findUnique({ where: { id: item.id } });
  }
}

export async function fetchResultsForEach(url: string) {
  const items: { id: number }[] = await (await fetch(url)).json();
  items.forEach((item) => {
    void prisma.user.findUnique({ where: { id: item.id } });
  });
}

export async function objectKeys(config: Record<string, number>) {
  for (const key of Object.keys(config)) {
    await prisma.team.findUnique({ where: { name: key } });
  }
}

export async function objectKeysOfOrmResult() {
  const team = await prisma.team.findFirst();
  for (const key of Object.keys(team ?? {})) {
    await prisma.team.findUnique({ where: { name: key } });
  }
}

export async function reassignedBeforeLoop() {
  let users = await prisma.user.findMany({ take: 10 });
  users = [];
  for (const user of users) {
    await prisma.task.count({ where: { assigneeId: user.id } });
  }
}

declare function loadIds(): Promise<number[]>;

export async function otherFunctionResult() {
  const ids = await loadIds();
  for (const id of ids) {
    await prisma.user.findUnique({ where: { id } });
  }
}

export async function stringSplit(csv: string) {
  return Promise.all(csv.split(",").map((name) => prisma.team.findUnique({ where: { name } })));
}

export async function indexedForLoop(count: number) {
  for (let i = 0; i < count; i++) {
    await prisma.user.findUnique({ where: { id: i } });
  }
}
