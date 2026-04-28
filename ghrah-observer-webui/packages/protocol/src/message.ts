import { z } from "zod";
import { ClientType } from "./enums.js";

export const GatewayMessageSchema = z.object({
  type: z.string(),
  payload: z.record(z.unknown()).optional().default({}),
  request_id: z.string().nullable().optional(),
  timestamp: z.number().nullable().optional(),
  client_type: z.nativeEnum(ClientType).nullable().optional(),
  seq_id: z.number().int().nullable().optional(),
});

export type GatewayMessage = z.infer<typeof GatewayMessageSchema>;

export function serializeMessage(message: GatewayMessage): string {
  const data = { ...message };
  if (data.timestamp == null) {
    data.timestamp = Date.now() / 1000;
  }
  return JSON.stringify(data);
}

export function parseMessage(raw: string): GatewayMessage {
  return GatewayMessageSchema.parse(JSON.parse(raw));
}
