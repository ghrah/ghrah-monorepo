import type { AbilityDefinitionPayload } from "@ghrah/protocol";

export const DEFAULT_ABILITIES: AbilityDefinitionPayload[] = [
  { ability_type: "read_file", params: {} },
  { ability_type: "write_file", params: {} },
  { ability_type: "edit_file", params: {} },
  { ability_type: "list_directory", params: {} },
  { ability_type: "execute_command", params: {} },
  { ability_type: "conversation", params: {} },
  { ability_type: "end_task", params: {} },
];
