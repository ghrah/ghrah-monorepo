// @vitest-environment happy-dom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import MessageInput from "./message-input.vue";

describe("MessageInput", () => {
  it("emits content on submit", async () => {
    const wrapper = mount(MessageInput, { props: { disabled: false } });
    await wrapper.find('input[type="text"]').setValue("hello room");
    await wrapper.find("form").trigger("submit");
    const sendEvents = wrapper.emitted("send");
    expect(sendEvents).toBeTruthy();
    expect(sendEvents![0]).toEqual(["hello room"]);
  });

  it("clears input after submit", async () => {
    const wrapper = mount(MessageInput, { props: { disabled: false } });
    const input = wrapper.find('input[type="text"]');
    await input.setValue("hi");
    await wrapper.find("form").trigger("submit");
    expect((input.element as HTMLInputElement).value).toBe("");
  });

  it("does not emit on empty content", async () => {
    const wrapper = mount(MessageInput, { props: { disabled: false } });
    await wrapper.find('input[type="text"]').setValue("   ");
    await wrapper.find("form").trigger("submit");
    expect(wrapper.emitted("send")).toBeFalsy();
  });

  it("disables input and button when disabled", () => {
    const wrapper = mount(MessageInput, { props: { disabled: true } });
    expect(wrapper.find('input[type="text"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('button[type="submit"]').attributes("disabled")).toBeDefined();
  });
});
