import { api } from "./api";

export type PushState = "loading" | "hidden" | "unsupported" | "blocked" | "off" | "on";

function toKey(value: string): Uint8Array {
  const padded = (value + "=".repeat((4 - (value.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

/** Reads whether this device is subscribed, and the server's public key. */
export async function pushStatus(): Promise<{ state: PushState; key?: string; message?: string }> {
  let cfg: { enabled: boolean; public_key: string | null };
  try {
    cfg = await api.get("/api/push/config");
  } catch {
    return { state: "hidden" };
  }
  if (!cfg.enabled || !cfg.public_key) return { state: "hidden" };
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
    return {
      state: "unsupported", key: cfg.public_key,
      message: ios ? "On iPhone, add SoloBiz to your Home Screen first, then turn notifications on here." : "This browser does not support notifications.",
    };
  }
  if (Notification.permission === "denied") {
    return { state: "blocked", key: cfg.public_key, message: "Notifications are blocked for this site in your browser settings." };
  }
  const reg = await registerServiceWorker();
  const sub = reg ? await (await navigator.serviceWorker.ready).pushManager.getSubscription() : null;
  return { state: sub ? "on" : "off", key: cfg.public_key };
}

export async function enablePush(key: string): Promise<void> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Notifications were not allowed.");
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toKey(key) as BufferSource });
  await api.post("/api/push/subscribe", { subscription: sub.toJSON() });
}

export async function disablePush(): Promise<void> {
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    await api.post("/api/push/unsubscribe", { endpoint: sub.endpoint });
    await sub.unsubscribe();
  }
}
