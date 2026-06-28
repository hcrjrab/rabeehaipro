"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api-client";
import { Bot, Cpu, ListTodo, Wifi } from "lucide-react";

export default function Dashboard() {
  const [info, setInfo] = useState<Record<string, unknown> | null>(null);
  const [tools, setTools] = useState<number>(0);
  const [providerCount, setProviderCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.info(),
      api.tools.list(),
      api.readiness(),
    ])
      .then(([infoData, toolsData, readyData]) => {
        setInfo(infoData);
        setTools(toolsData.length);
        setProviderCount((readyData.providers ?? []).length);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const statCards = [
    { title: "Agents", value: "11", icon: Bot, desc: "Active agent roles" },
    { title: "Tools", value: String(tools || "..."), icon: Cpu, desc: "Registered tools" },
    { title: "Providers", value: String(providerCount || "..."), icon: Wifi, desc: "LLM providers" },
    { title: "API Status", value: info ? (info as any).env ?? "online" : "...", icon: ListTodo, desc: "Backend environment" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">System overview and quick actions.</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <Card key={card.title}>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                {loading ? (
                  <Skeleton className="h-8 w-20" />
                ) : (
                  <div className="text-2xl font-bold">{card.value}</div>
                )}
                <p className="text-xs text-muted-foreground">{card.desc}</p>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>System Info</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {loading ? (
              <Skeleton className="h-20" />
            ) : (
              <>
                <div className="flex justify-between"><span className="text-muted-foreground">App</span><span>{(info as any)?.app_name ?? "Rabeeh AI"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Env</span><Badge variant="outline">{(info as any)?.env ?? "dev"}</Badge></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Provider</span><span>{(info as any)?.default_provider ?? "mock"}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Model</span><span>{(info as any)?.ollama_default_model ?? "—"}</span></div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex items-center gap-2 rounded-lg border p-3">
              <span>Run a task in the Chat view, or check agent status in Agents.</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
