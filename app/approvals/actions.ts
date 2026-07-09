"use server";

// Server actions behind the /approvals review desk. Both funnel into the
// database's atomic review functions; the page re-renders with fresh data
// after every decision.

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { reviewCorrection } from "@/lib/corrections";

async function decide(decision: "approve" | "reject", formData: FormData) {
  const id = Number(formData.get("id"));
  if (!Number.isInteger(id) || id <= 0) {
    redirect(`/approvals?error=${encodeURIComponent("Invalid correction id.")}`);
  }
  let error: string | null;
  try {
    error = await reviewCorrection(decision, id);
  } catch (cause) {
    error = cause instanceof Error ? cause.message : "Unexpected error.";
  }
  revalidatePath("/approvals");
  if (error) {
    redirect(`/approvals?error=${encodeURIComponent(error)}`);
  }
}

export async function approveCorrection(formData: FormData) {
  await decide("approve", formData);
}

export async function rejectCorrection(formData: FormData) {
  await decide("reject", formData);
}
