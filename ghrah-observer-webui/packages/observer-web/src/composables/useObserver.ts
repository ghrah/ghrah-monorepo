import { connectStores, ObserverClient, useConnectionStore } from "@ghrah/observer-core";
import { ref, shallowRef } from "vue";

export function useObserver() {
  const connection = useConnectionStore();

  const client = shallowRef<ObserverClient | null>(null);
  const error = ref<string | null>(null);

  async function connect(gatewayUrl?: string) {
    const url = gatewayUrl ?? connection.gatewayUrl;
    connection.setConnecting();
    error.value = null;

    try {
      const obsClient = new ObserverClient(url);
      connectStores(obsClient);

      obsClient.onConnected(() => connection.setConnected());
      obsClient.onDisconnected(() => connection.setDisconnected());
      obsClient.onReconnecting(() => connection.setReconnecting());
      obsClient.onReconnected(() => connection.setConnected());

      await obsClient.connect();
      client.value = obsClient;
    } catch (err) {
      connection.setDisconnected();
      error.value = err instanceof Error ? err.message : String(err);
    }
  }

  async function disconnect() {
    if (client.value) {
      await client.value.disconnect();
      client.value = null;
    }
    connection.setDisconnected();
  }

  return {
    client,
    connection,
    error,
    connect,
    disconnect,
  };
}
