import { prisma } from "./db";

// No Prisma call here is inside a loop: loopContext must be null.

export async function ormCallAsIterable() {
  const names: string[] = [];
  for (const team of await prisma.team.findMany({ take: 10 })) {
    names.push(team.name);
  }
  return names;
}

class Registry {
  find(cb: (value: number) => boolean) {
    return cb(1);
  }
}

export async function customFindMethod(registry: Registry) {
  registry.find(() => {
    void prisma.user.count();
    return true;
  });
}

export async function callbackOfNonIterationMethod() {
  setTimeout(() => {
    void prisma.user.count();
  }, 10);
}
