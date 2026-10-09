import { redirect } from "next/navigation";
import LoginForm from "@/components/LoginForm";
import { ApiError, serverApi } from "@/lib/server";

export default async function LoginPage() {
  let authed = true;
  try {
    await serverApi("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) authed = false;
    else throw e;
  }
  if (authed) redirect("/dashboard");
  return <LoginForm />;
}
