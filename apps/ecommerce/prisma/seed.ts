import { PrismaPg } from "@prisma/adapter-pg";
import { OrderStatus, PaymentMethod, PrismaClient } from "../src/generated/prisma/client.js";
import { createRng, dateBetween, int, pick, sample, sentence, slugify, uuid, words } from "./random.js";

const COUNTS = {
  customers: 3_000,
  products: 5_000,
  orders: 20_000,
  reviews: 15_000,
};

const CATEGORY_NAMES = [
  "Audio", "Cameras", "Computers", "Phones", "Wearables", "Gaming", "Home Office",
  "Kitchen", "Furniture", "Lighting", "Bedding", "Bath", "Garden", "Tools",
  "Outdoor", "Fitness", "Cycling", "Camping", "Books", "Stationery", "Toys",
  "Pet Supplies", "Beauty", "Apparel",
] as const;

const ADJECTIVES = [
  "Ergonomic", "Compact", "Wireless", "Portable", "Premium", "Classic", "Smart",
  "Durable", "Lightweight", "Modular", "Rustic", "Sleek", "Heavy-Duty", "Eco",
] as const;
const MATERIALS = [
  "Steel", "Oak", "Bamboo", "Cotton", "Leather", "Aluminium", "Ceramic", "Glass",
  "Linen", "Carbon", "Wool", "Granite",
] as const;
const NOUNS = [
  "Chair", "Lamp", "Speaker", "Backpack", "Kettle", "Keyboard", "Monitor Stand",
  "Headphones", "Bottle", "Blanket", "Desk", "Tripod", "Mat", "Organizer",
  "Charger", "Tent", "Watch", "Mug", "Planter", "Shelf",
] as const;
const FIRST_NAMES = [
  "Amina", "Rafi", "Nadia", "Tanvir", "Sara", "Imran", "Leila", "Omar", "Priya",
  "Arjun", "Mei", "Kenji", "Lucia", "Mateo", "Hannah", "Jonas", "Zara", "Yusuf",
  "Elena", "Noah",
] as const;
const LAST_NAMES = [
  "Rahman", "Hossain", "Chowdhury", "Khan", "Ahmed", "Sharma", "Tanaka", "Garcia",
  "Muller", "Rossi", "Silva", "Novak", "Kowalski", "Haddad", "Okafor", "Lee",
] as const;
const VOCABULARY = [
  "quality", "delivery", "value", "design", "comfortable", "sturdy", "quick",
  "recommend", "price", "works", "great", "solid", "battery", "finish", "size",
  "daily", "use", "packaging", "excellent", "decent", "easy", "setup", "colour",
  "feels", "premium", "returned", "gift", "perfect", "material", "support",
] as const;

const RATING_WEIGHTS = [1, 1, 2, 3, 3, 4, 4, 5, 5, 5] as const;
const PAYMENT_METHOD_WEIGHTS = [
  ...Array<PaymentMethod>(14).fill(PaymentMethod.CARD),
  ...Array<PaymentMethod>(5).fill(PaymentMethod.PAYPAL),
  PaymentMethod.BANK_TRANSFER,
] as const;
const DAY_MS = 24 * 60 * 60 * 1000;

function hex(rng: () => number, length: number): string {
  return Array.from({ length }, () => Math.floor(rng() * 16).toString(16)).join("");
}

function generate() {
  const rng = createRng(20260925);
  // Columns added after the initial schema draw from their own stream so the
  // original columns keep generating identical values.
  const extra = createRng(20260926);
  const now = new Date("2026-09-01T00:00:00Z");
  const twoYearsAgo = new Date(now.getTime() - 730 * DAY_MS);
  const oneYearAgo = new Date(now.getTime() - 365 * DAY_MS);

  const categories = CATEGORY_NAMES.map((name) => ({
    id: uuid(rng),
    name,
    slug: slugify(name),
    createdAt: twoYearsAgo,
  }));

  const customers = Array.from({ length: COUNTS.customers }, (_, i) => {
    const first = pick(rng, FIRST_NAMES);
    const last = pick(rng, LAST_NAMES);
    return {
      id: uuid(rng),
      email: `${first}.${last}.${i}@example.com`.toLowerCase(),
      name: `${first} ${last}`,
      createdAt: dateBetween(rng, twoYearsAgo, now),
      phone: extra() < 0.96 ? `+8801${int(extra, 3, 9)}${String(int(extra, 0, 99_999_999)).padStart(8, "0")}` : null,
      marketingOptIn: extra() < 0.3,
    };
  });

  const products = Array.from({ length: COUNTS.products }, (_, i) => ({
    id: uuid(rng),
    sku: `SKU-${String(i + 1).padStart(6, "0")}`,
    name: `${pick(rng, ADJECTIVES)} ${pick(rng, MATERIALS)} ${pick(rng, NOUNS)}`,
    description: sentence(rng, VOCABULARY, 15, 40),
    priceCents: int(rng, 199, 49_999),
    stock: int(rng, 0, 500),
    categoryId: pick(rng, categories).id,
    createdAt: dateBetween(rng, twoYearsAgo, oneYearAgo),
  }));

  const orders: {
    id: string;
    customerId: string;
    status: OrderStatus;
    totalCents: number;
    paymentMethod: PaymentMethod;
    paymentReference: string;
    shippingPostcode: string | null;
    createdAt: Date;
  }[] = [];
  const orderItems: {
    id: string;
    orderId: string;
    productId: string;
    quantity: number;
    unitPriceCents: number;
  }[] = [];

  for (let i = 0; i < COUNTS.orders; i++) {
    const id = uuid(rng);
    const createdAt = dateBetween(rng, oneYearAgo, now);
    const ageDays = (now.getTime() - createdAt.getTime()) / DAY_MS;
    const status: OrderStatus =
      rng() < 0.05
        ? OrderStatus.CANCELLED
        : ageDays > 14
          ? OrderStatus.DELIVERED
          : pick(rng, [OrderStatus.PENDING, OrderStatus.PAID, OrderStatus.SHIPPED]);

    let totalCents = 0;
    for (const product of sample(rng, products, int(rng, 1, 4))) {
      const quantity = int(rng, 1, 3);
      totalCents += quantity * product.priceCents;
      orderItems.push({
        id: uuid(rng),
        orderId: id,
        productId: product.id,
        quantity,
        unitPriceCents: product.priceCents,
      });
    }

    orders.push({
      id,
      customerId: pick(rng, customers).id,
      status,
      totalCents,
      paymentMethod: pick(extra, PAYMENT_METHOD_WEIGHTS),
      paymentReference: `ch_${hex(extra, 24)}`,
      shippingPostcode: extra() < 0.97 ? String(int(extra, 1000, 9499)) : null,
      createdAt,
    });
  }

  const reviews = Array.from({ length: COUNTS.reviews }, () => ({
    id: uuid(rng),
    productId: pick(rng, products).id,
    customerId: pick(rng, customers).id,
    rating: pick(rng, RATING_WEIGHTS),
    title: sentence(rng, VOCABULARY, 2, 6),
    body: words(rng, VOCABULARY, 20, 80),
    createdAt: dateBetween(rng, oneYearAgo, now),
  }));

  return { categories, customers, products, orders, orderItems, reviews };
}

async function main() {
  const prisma = new PrismaClient({
    adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL }),
  });

  try {
    if ((await prisma.product.count()) > 0) {
      console.log("ecommerce: database already seeded, skipping");
      return;
    }

    const data = generate();

    await prisma.$transaction([
      prisma.category.createMany({ data: data.categories }),
      prisma.customer.createMany({ data: data.customers }),
      prisma.product.createMany({ data: data.products }),
      prisma.order.createMany({ data: data.orders }),
      prisma.orderItem.createMany({ data: data.orderItems }),
      prisma.review.createMany({ data: data.reviews }),
    ]);

    console.log(
      `ecommerce: seeded ${data.categories.length} categories, ${data.customers.length} customers, ` +
        `${data.products.length} products, ${data.orders.length} orders, ` +
        `${data.orderItems.length} order items, ${data.reviews.length} reviews`,
    );
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
