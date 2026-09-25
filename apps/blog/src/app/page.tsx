const ENDPOINTS = [
  "GET /api/posts?tag=&cursor=&limit=",
  "GET /api/posts/:slug",
  "GET /api/posts/:slug/comments?cursor=&limit=",
  "GET /api/posts/search?q=&limit=",
  "GET /api/authors/:id",
  "GET /api/tags",
  "GET /api/stats",
];

export default function Home() {
  return (
    <main>
      <h1>Blog test application</h1>
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
