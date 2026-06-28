"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/theme-toggle";
import { Settings, Bell, Shield, Wifi } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Settings className="h-5 w-5 text-primary" />
        <h1 className="text-xl font-bold tracking-tight">Settings</h1>
      </div>

      <Card>
        <CardHeader><CardTitle>Appearance</CardTitle></CardHeader>
        <CardContent className="flex items-center justify-between">
          <span className="text-sm">Theme</span>
          <ThemeToggle />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>LLM Configuration</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Provider</label>
            <Input defaultValue="mock" placeholder="e.g. openai, anthropic, ollama" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Model</label>
            <Input defaultValue="mock/gpt-4o" placeholder="e.g. gpt-4o, claude-3-opus" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">API Base URL</label>
            <Input defaultValue="http://localhost:11434" placeholder="http://localhost:11434" />
          </div>
          <Button variant="outline">Test Connection</Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Notifications</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-sm font-medium">Task Notifications</span>
              <p className="text-xs text-muted-foreground">Get notified when tasks complete or fail</p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-sm font-medium">Approval Alerts</span>
              <p className="text-xs text-muted-foreground">Prompt when a task requires approval</p>
            </div>
            <Switch defaultChecked />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Security</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-sm font-medium">Require Approval</span>
              <p className="text-xs text-muted-foreground">High-risk actions require manual approval</p>
            </div>
            <Switch defaultChecked />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-sm font-medium">Sandboxed Execution</span>
              <p className="text-xs text-muted-foreground">Run code in isolated sandbox</p>
            </div>
            <Switch defaultChecked />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
