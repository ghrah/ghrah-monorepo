import { defineStore } from "pinia";
import { ref } from "vue";

export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

export const useConnectionStore = defineStore("ghrah-connection", () => {
  const state = ref<ConnectionState>("disconnected");
  const gatewayUrl = ref("ws://localhost:4111/ws");

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

  function setGatewayUrl(url: string) {
    gatewayUrl.value = url;
  }

  return {
    state,
    gatewayUrl,
    setConnected,
    setDisconnected,
    setConnecting,
    setReconnecting,
    setGatewayUrl,
  };
});
