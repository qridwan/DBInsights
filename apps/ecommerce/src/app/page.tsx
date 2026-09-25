const ENDPOINTS = [
  "GET /api/products?categoryId=&cursor=&limit=",
  "GET /api/products/:id",
  "GET /api/products/search?q=&limit=",
  "GET /api/categories",
  "GET /api/customers/:id/orders?cursor=&limit=",
  "GET /api/orders/:id",
  "GET /api/stats/sales?days=",
  "GET /api/stats/categories",
];

export default function Home() {
  return (
    <main>
      <h1>Ecommerce test application</h1>
      <p>DBInsight test target. API endpoints:</p>
      <ul>
        {ENDPOINTS.map((endpoint) => (
          <li key={endpoint}>
            <code>{endpoint}</code>
          </li>
        ))}
      </ul>
    </main>
  );
}
