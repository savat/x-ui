import UsersClient from "@/components/UsersClient";
import { serverApi } from "@/lib/server";
import type { User } from "@/lib/types";

export default async function UsersPage() {
  const initial = await serverApi<User[]>("/users");
  return <UsersClient initial={initial} />;
}
