import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import { useConnectionStore } from "./connection.js";

describe("useConnectionStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("initial state is disconnected", () => {
    const store = useConnectionStore();
    expect(store.state).toBe("disconnected");
  });

  it("default serverUrl is ws://localhost:4112/ws", () => {
    const store = useConnectionStore();
    expect(store.serverUrl).toBe("ws://localhost:4112/ws");
  });

  it("setConnected changes state to connected", () => {
    const store = useConnectionStore();
    store.setConnected();
    expect(store.state).toBe("connected");
  });

  it("setDisconnected changes state to disconnected", () => {
    const store = useConnectionStore();
    store.setConnected();
    store.setDisconnected();
    expect(store.state).toBe("disconnected");
  });

  it("setConnecting changes state to connecting", () => {
    const store = useConnectionStore();
    store.setConnecting();
    expect(store.state).toBe("connecting");
  });

  it("setReconnecting changes state to reconnecting", () => {
    const store = useConnectionStore();
    store.setReconnecting();
    expect(store.state).toBe("reconnecting");
  });

  it("setServerUrl updates the url", () => {
    const store = useConnectionStore();
    store.setServerUrl("ws://other:9999/ws");
    expect(store.serverUrl).toBe("ws://other:9999/ws");
  });

  it("state transitions work in sequence", () => {
    const store = useConnectionStore();
    expect(store.state).toBe("disconnected");

    store.setConnecting();
    expect(store.state).toBe("connecting");

    store.setConnected();
    expect(store.state).toBe("connected");

    store.setDisconnected();
    expect(store.state).toBe("disconnected");

    store.setReconnecting();
    expect(store.state).toBe("reconnecting");
  });
});
