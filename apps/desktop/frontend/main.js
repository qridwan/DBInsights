// The splash screen: shows the services starting and hands over to the dashboard when they are up.
// It talks to the Rust side through Tauri's global API (withGlobalTauri).
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const { open } = window.__TAURI__.dialog;

const $ = (id) => document.getElementById(id);
const rows = Object.fromEntries([...document.querySelectorAll("[data-step]")].map((li) => [li.dataset.step, li]));
let failed = false;

function setStep(step, state, detail) {
  const li = rows[step];
  if (!li) return;
  li.className = state;
  if (detail) li.querySelector(".detail").textContent = detail;
}

function showFailure(step) {
  failed = true;
  $("title").textContent = "DBInsight could not start";
  $("subtitle").textContent = "Read the message below, fix it, and try again.";
  $("actions").classList.add("show");
  showLog(step === "database" ? "docker" : step);
}

async function showLog(name) {
  const text = await invoke("read_log", { name, lines: 60 }).catch((e) => String(e));
  const view = $("logview");
  view.textContent = text || "(no output yet)";
  view.classList.add("show");
  view.scrollTop = view.scrollHeight;
}

async function start() {
  failed = false;
  $("actions").classList.remove("show");
  $("logview").classList.remove("show");
  $("title").textContent = "Starting DBInsight";
  $("subtitle").textContent = "Getting the database, the API and the dashboard ready.";
  for (const step of Object.keys(rows)) setStep(step, "waiting");
  const config = await invoke("get_config");
  $("homenote").innerHTML = config.home ? `Using <code>${config.home}</code>` : "";
  if (!config.home_ok) {
    $("title").textContent = "Where is DBInsight?";
    $("subtitle").textContent = "Choose the folder you cloned DBInsight into (the one that contains apps, services and packages).";
    $("actions").classList.add("show");
    return;
  }
  await invoke("start_services");
}

listen("service-status", ({ payload }) => {
  setStep(payload.step, payload.state, payload.detail);
  if (payload.state === "error") showFailure(payload.step);
});
listen("services-ready", () => {
  $("title").textContent = "Opening DBInsight";
  $("subtitle").textContent = "";
});

$("retry").addEventListener("click", start);
$("logs").addEventListener("click", () => showLog("api"));
$("openlogs").addEventListener("click", () => invoke("open_logs_folder"));
$("folder").addEventListener("click", async () => {
  const chosen = await open({ directory: true, multiple: false, title: "Choose the DBInsight folder" });
  if (!chosen) return;
  try {
    await invoke("set_home", { path: chosen });
    await start();
  } catch (error) {
    $("subtitle").textContent = String(error);
    $("actions").classList.add("show");
  }
});

start();
