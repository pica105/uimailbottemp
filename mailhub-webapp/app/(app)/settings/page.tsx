"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Save, CheckCircle2 } from "lucide-react";
import { useSettings, useUpdateSettings } from "@/hooks/useMessages";
import { useT } from "@/lib/i18n";
import { useAppStore } from "@/stores/appStore";
import type { Language } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { LanguageSelector } from "@/components/settings/LanguageSelector";
import { PollingInterval } from "@/components/settings/PollingInterval";
import { MutedCategories } from "@/components/settings/MutedCategories";
import { AccountsList } from "@/components/settings/AccountsList";

const settingsSchema = z.object({
  language: z.enum(["ru", "en"]),
  muted_categories: z.array(z.enum(["promo", "spam", "social", "other"])),
});

type SettingsForm = z.infer<typeof settingsSchema>;

export default function SettingsPage() {
  const { t } = useT();
  const { data, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const setLanguage = useAppStore((s) => s.setLanguage);
  const [savedFlash, setSavedFlash] = useState(false);

  const form = useForm<SettingsForm>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      language: "en",
      muted_categories: [],
    },
  });

  // Hydrate the form when settings arrive.
  useEffect(() => {
    if (data) {
      const s = data.settings;
      form.reset({
        language: s.language,
        muted_categories: s.muted_categories,
      });
      setLanguage(s.language);
    }
  }, [data, form, setLanguage]);

  const onSubmit = (values: SettingsForm) => {
    updateSettings.mutate(
      {
        language: values.language,
        muted_categories: values.muted_categories,
      },
      {
        onSuccess: () => {
          setSavedFlash(true);
          setTimeout(() => setSavedFlash(false), 2000);
        },
      },
    );
  };

  if (isLoading && !data) {
    return (
      <main className="space-y-4">
        <Skeleton className="h-12 w-40" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </main>
    );
  }

  const muted = form.watch("muted_categories");

  return (
    <main className="space-y-4">
      <h1 className="text-xl font-bold">{t("settings.title")}</h1>

      <Card>
        <CardContent className="space-y-6 pt-5">
          <LanguageSelector
            value={form.watch("language") as Language}
            onChange={(lang) => form.setValue("language", lang, { shouldDirty: true })}
          />
          <PollingInterval />
          <MutedCategories
            value={muted}
            onChange={(cats) =>
              form.setValue("muted_categories", cats, { shouldDirty: true })
            }
          />
        </CardContent>
      </Card>

      <Button
        className="w-full"
        size="lg"
        onClick={form.handleSubmit(onSubmit)}
        disabled={updateSettings.isPending}
      >
        {savedFlash ? <CheckCircle2 /> : <Save />}
        {savedFlash ? t("settings.saved") : t("settings.save")}
      </Button>

      <AccountsList accounts={data?.settings.accounts ?? []} />
    </main>
  );
}
