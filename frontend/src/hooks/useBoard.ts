import { api } from "../api/client";
import type { BoardId, WindowDays } from "../api/types";
import { useFetch } from "./useFetch";

export function useBoard(board: BoardId, window: WindowDays, cuisine: string, borough: string) {
  return useFetch(`${board}|${window}|${cuisine}|${borough}`, (signal) => api.boards(board, window, cuisine, borough, signal));
}
