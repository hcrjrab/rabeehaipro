"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api-client";
import { Bot, Brain, Code, Globe, Monitor, Eye, FileText, FileSpreadsheet, Wrench, Users, ClipboardCheck } from "lucide-react";

const agentIcons: Record<string, React.ReactNode> = {
  planner: <Brain className="h-4 w-4" />,
  reviewer: <ClipboardCheck className="h-4 w-4" />,
  research: <Globe className="h-4 w-4" />,
  coding: <Code className="h-4 w-4" />,
  browser: <Monitor className="h-4 w-4" />,
  automation: <Wrench className="h-4 w-4" />,
  file: <FileText className="h-4 w-4" />,
  vision: <Eye className="h-4 w-4" />,
  office: <FileSpreadsheet className="h-4 w-4" />,
  business: <Users className="h-4 w-4" />,
  memory: <Brain className="h-4 w-4" />,
};

const agentDescriptions: Record<string, string> = {
  planner: "Breaks down goals into multi-step plans",
  reviewer: "Reviews & validates agent outputs",
  research: "Web research with DuckDuckGo & Tavily",
  coding: "Writes & runs Python/Node.js code in sandbox",
  browser: "Controls Playwright browser",
  automation: "Runs shell commands & scripts",
  file: "Reads & writes project files",
  vision: "Analyzes images via LLM vision",
  office: "Reads/writes Excel, Word, PDF files",
  business: "Business logic: CRM, invoices, BOQ",
  memory: "Manages vector + graph memory",
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Array<{ role: string; name: string }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.agents.list().then(setAgents).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const allAgents = agents.length > 0
    ? agents
    : Object.entries(agentDescriptions).map(([role, _]) => ({ role, name: role.charAt(0).toUpperCase() + role.slice(1) }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Bot className="h-5 w-5 text-primary" />
        <h1 className="text-xl font-bold tracking-tight">Agents</h1>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {loading
          ? [1, 2, 3, 4, 5, 6].map((i) => (
              <Card key={i}>
                <CardHeader><Skeleton className="h-4 w-24" /></CardHeader>
                <CardContent><Skeleton className="h-4 w-40" /></CardContent>
              </Card>
            ))
          : allAgents.map((agent) => (
              <Card key={agent.role}>
                <CardHeader className="flex flex-row items-center gap-3 pb-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
                    {agentIcons[agent.role] ?? <Bot className="h-4 w-4" />}
                  </div>
                  <CardTitle className="text-sm font-medium capitalize">
                    {agent.name}
                  </CardTitle>
                  <Badge variant="secondary" className="ml-auto text-xs">
                    {agent.role}
                  </Badge>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-muted-foreground">
                    {agentDescriptions[agent.role] ?? "Agent available"}
                  </p>
                </CardContent>
              </Card>
            ))}
      </div>
    </div>
  );
}
