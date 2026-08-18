"use client";

import { useMutation, useQuery } from "@apollo/client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  EmptyState,
  QueryError,
  TableSkeleton,
} from "@/components/query-states";
import { getAccessToken } from "@/lib/auth";
import {
  CREATE_USER,
  DEACTIVATE_USER,
  ME,
  USERS,
} from "@/lib/graphql/operations";

type UserRow = {
  id: string;
  email: string;
  role: string;
  isActive: boolean;
  dateJoined: string;
};

type UsersResult = { users: UserRow[] };
type MeResult = { me: { id: string; role: string } };

type CreateForm = {
  email: string;
  password: string;
  role: "ADMIN" | "FINANCE" | "NURSE" | "PRO";
};

const ROLES = ["ADMIN", "FINANCE", "NURSE", "PRO"] as const;

export default function UsersPage() {
  const router = useRouter();

  const hasToken = getAccessToken() !== null;
  useEffect(() => {
    if (!hasToken) router.replace("/login");
  }, [hasToken, router]);

  const { data: meData, loading: meLoading } = useQuery<MeResult>(ME, {
    skip: !hasToken,
  });
  const isAdmin = meData?.me.role === "ADMIN";
  const myId = meData?.me.id;

  const {
    data,
    loading,
    error: usersError,
    refetch: refetchUsers,
  } = useQuery<UsersResult>(USERS, {
    skip: !hasToken || !isAdmin,
  });

  const { register, handleSubmit, reset } = useForm<CreateForm>({
    defaultValues: { email: "", password: "", role: "NURSE" },
  });

  const refetch = [{ query: USERS }];
  const [createUser, { loading: creating, error: createError }] = useMutation(
    CREATE_USER,
    { refetchQueries: refetch, onCompleted: () => reset(), onError: () => {} }
  );
  const [deactivateUser, { error: deactivateError }] = useMutation(
    DEACTIVATE_USER,
    { refetchQueries: refetch, onError: () => {} }
  );

  function onCreate(values: CreateForm) {
    createUser({ variables: values });
  }

  if (!hasToken || meLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center p-4 sm:p-6 lg:p-8">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </main>
    );
  }

  if (!isAdmin) {
    return (
      <main className="mx-auto min-h-screen max-w-2xl p-4 sm:p-6 lg:p-8">
        <Card>
          <CardHeader>
            <CardTitle>Not authorized</CardTitle>
            <CardDescription>
              User management is available to Admin only.
            </CardDescription>
          </CardHeader>
        </Card>
      </main>
    );
  }

  const users = data?.users ?? [];

  return (
    <main className="mx-auto min-h-screen max-w-3xl space-y-6 p-4 sm:p-6">
      <h1 className="text-xl font-semibold">User management</h1>

      {/* User list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Users</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <TableSkeleton rows={4} cols={4} />
          ) : usersError ? (
            <QueryError
              message={usersError.message}
              onRetry={() => refetchUsers()}
            />
          ) : users.length === 0 ? (
            <EmptyState title="No users" />
          ) : (
            <>
              {/* Mobile: stacked cards */}
              <div className="space-y-2.5 sm:hidden">
                {users.map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center justify-between gap-3 rounded-lg border bg-card p-3"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {u.email}
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {u.role}
                        </span>
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${
                            u.isActive
                              ? "bg-green-100 text-green-800"
                              : "bg-gray-200 text-gray-600"
                          }`}
                        >
                          {u.isActive ? "Active" : "Inactive"}
                        </span>
                      </div>
                    </div>
                    {u.isActive && u.id !== myId ? (
                      <button
                        type="button"
                        className="shrink-0 text-xs font-medium text-red-600 active:underline"
                        onClick={() =>
                          deactivateUser({ variables: { userId: u.id } })
                        }
                      >
                        Deactivate
                      </button>
                    ) : u.id === myId ? (
                      <span className="shrink-0 text-xs text-muted-foreground">
                        You
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>

              {/* Tablet/desktop: table */}
              <div className="hidden overflow-x-auto sm:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-2 pr-4 font-medium">Email</th>
                      <th className="py-2 pr-4 font-medium">Role</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id} className="border-b last:border-0">
                        <td className="py-2 pr-4">{u.email}</td>
                        <td className="py-2 pr-4">{u.role}</td>
                        <td className="py-2 pr-4">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                              u.isActive
                                ? "bg-green-100 text-green-800"
                                : "bg-gray-200 text-gray-600"
                            }`}
                          >
                            {u.isActive ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="py-2 text-right">
                          {u.isActive && u.id !== myId ? (
                            <button
                              type="button"
                              className="text-xs text-red-600 hover:underline"
                              onClick={() =>
                                deactivateUser({ variables: { userId: u.id } })
                              }
                            >
                              Deactivate
                            </button>
                          ) : u.id === myId ? (
                            <span className="text-xs text-muted-foreground">
                              You
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {deactivateError ? (
                <p className="mt-2 text-sm text-red-600">
                  {deactivateError.message}
                </p>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>

      {/* Create user */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add user</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={handleSubmit(onCreate)}
            className="grid gap-4 sm:grid-cols-2"
          >
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="off"
                {...register("email", { required: true })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                {...register("password", { required: true, minLength: 8 })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role">Role</Label>
              <select
                id="role"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                {...register("role")}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <Button type="submit" disabled={creating}>
                {creating ? "Creating…" : "Create user"}
              </Button>
            </div>
            {createError ? (
              <p className="text-sm text-red-600 sm:col-span-2">
                {createError.message}
              </p>
            ) : null}
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
