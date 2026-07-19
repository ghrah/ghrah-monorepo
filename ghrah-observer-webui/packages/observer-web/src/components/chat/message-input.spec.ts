// @vitest-environment happy-dom

import { useAgentsStore } from "@ghrah/observer-core";
import type { AgentSpawnedPayload } from "@ghrah/protocol";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";
import MessageInput from "./message-input.vue";

function spawn(name: string) {
  return { type: "agent_spawned", name, config: { name } } as unknown as AgentSpawnedPayload;
}

function mountInput() {
  return mount(MessageInput, { props: { disabled: false } });
}

async function setInputs(wrapper: ReturnType<typeof mountInput>, text: string, targets: string[]) {
  const input = wrapper.find('input[type="text"]');
  await input.setValue(text);
  // toggle target chips by name
  for (const t of targets) {
    const chips = wrapper.findAll("button[type=button]");
    const chip = chips.filter((c) => c.text().includes(`@${t}`));
    for (const c of chip) await c.trigger("click");
  }
}

describe("MessageInput", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("emits targets+content from leading @mention", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    const wrapper = mountInput();
    await setInputs(wrapper, "@B hello", []);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    const sendEvents = wrapper.emitted("send");
    expect(sendEvents).toBeTruthy();
    expect(sendEvents![0]).toEqual([["B"], "hello"]);
  });

  it("emits targets from multi-select chips", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    agents.onAgentSpawned(spawn("C"));
    const wrapper = mountInput();
    await setInputs(wrapper, "hi", ["B", "C"]);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    const sendEvents = wrapper.emitted("send");
    expect(sendEvents).toBeTruthy();
    const [targets, content] = sendEvents![0] as [string[], string];
    expect(targets.sort()).toEqual(["B", "C"]);
    expect(content).toBe("hi");
  });

  it("merges leading @mention with chip selection", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    agents.onAgentSpawned(spawn("C"));
    const wrapper = mountInput();
    await setInputs(wrapper, "@B hello", ["C"]);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    const [targets, content] = wrapper.emitted("send")![0] as [string[], string];
    expect(targets.sort()).toEqual(["B", "C"]);
    expect(content).toBe("hello");
  });

  it("does not emit when no target selected and no @mention", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    const wrapper = mountInput();
    await setInputs(wrapper, "hello", []);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("send")).toBeFalsy();
  });

  it("does not emit when content empty", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    const wrapper = mountInput();
    await setInputs(wrapper, "", ["B"]);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("send")).toBeFalsy();
  });

  it("does not emit when bare @mention has no content", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    const wrapper = mountInput();
    await setInputs(wrapper, "@B", []);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("send")).toBeFalsy();
  });

  it("parses concatenated leading @mentions (@B@C hello)", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    agents.onAgentSpawned(spawn("C"));
    const wrapper = mountInput();
    await setInputs(wrapper, "@B@C hello", []);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    const sendEvents = wrapper.emitted("send");
    expect(sendEvents).toBeTruthy();
    const [targets, content] = sendEvents![0] as [string[], string];
    expect(targets.sort()).toEqual(["B", "C"]);
    expect(content).toBe("hello");
  });

  it("does not parse unknown @name as target", async () => {
    const agents = useAgentsStore();
    agents.onAgentSpawned(spawn("B"));
    const wrapper = mountInput();
    // 未知名 ghost 不在 activeAgents；@ghost hello 应整体作 content，无 target（除非 chip）
    await setInputs(wrapper, "@ghost hello", []);
    wrapper.find("form").trigger("submit");
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted("send")).toBeFalsy();
  });
});

it("merges leading @mention with chip selection", async () => {
  const agents = useAgentsStore();
  agents.onAgentSpawned(spawn("B"));
  agents.onAgentSpawned(spawn("C"));
  const wrapper = mountInput();
  await setInputs(wrapper, "@B hello", ["C"]);
  wrapper.find("form").trigger("submit");
  await wrapper.vm.$nextTick();
  const [targets, content] = wrapper.emitted("send")![0] as [string[], string];
  expect(targets.sort()).toEqual(["B", "C"]);
  expect(content).toBe("hello");
});
