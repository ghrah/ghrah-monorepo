import { defineStore } from "pinia";
import { ref } from "vue";

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

export const useConnectionStore = defineStore("ghrah-connection", () => {
  const state = ref<ConnectionState>("disconnected");
  const serverUrl = ref("ws://localhost:4112/ws");

  function setConnected() {
    state.value = "connected";
  }

  function setDisconnected() {
    state.value = "disconnected";
  }

  function setConnecting() {
    state.value = "connecting";
  }

  function setReconnecting() {
    state.value = "reconnecting";
  }

  function setServerUrl(url: string) {
    serverUrl.value = url;
  }

  return {
    state,
    serverUrl,
    setConnected,
    setDisconnected,
    setConnecting,
    setReconnecting,
    setServerUrl,
  };
});
