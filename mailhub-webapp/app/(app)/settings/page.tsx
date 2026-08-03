"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { CheckCircle2, Save } from "lucide-react";
import { useSettings, useUpdateSettings } from "@/hooks/useMessages";
import { useT } from "@/lib/i18n";
import { useAppStore } from "@/stores/appStore";
import type { Language } from "@/types";
import { BlobButton } from "@/components/ui/blob-button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ThemeToggle } from "@/components/settings/ThemeToggle";
import { LanguageSelector } from "@/components/settings/LanguageSelector";
import { MutedCategories } from "@/components/settings/MutedCategories";

const settingsSchema = z.object({
  language: z.enum(["ru", "en"]),
  muted_categories: z.array(z.string()),
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

  const isDirty = form.formState.isDirty;
  const muted = form.watch("muted_categories");
  const categories = data?.settings.categories ?? [];

  // Hydrate the form when settings arrive (categories re-fetch each open).
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
          form.reset({
            language: values.language,
            muted_categories: values.muted_categories,
          });
          window.setTimeout(() => setSavedFlash(false), 2000);
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

  return (
    <main className="space-y-4">
      <h1 className="glow text-xl font-bold">{t("settings.title")}</h1>

      <Card>
        <CardContent className="space-y-6 pt-5">
          {/* Theme applies immediately, like the category switcher. */}
          <ThemeToggle />
          <LanguageSelector
            value={form.watch("language") as Language}
            onChange={(lang) => form.setValue("language", lang, { shouldDirty: true })}
          />
          <MutedCategories
            value={muted}
            categories={categories}
            onChange={(cats) =>
              form.setValue("muted_categories", cats, { shouldDirty: true })
            }
          />
        </CardContent>
      </Card>

      <BlobButton
        className="w-full"
        size="lg"
        onClick={form.handleSubmit(onSubmit)}
        disabled={updateSettings.isPending || !isDirty}
        aria-disabled={!isDirty}
      >
        {savedFlash ? <CheckCircle2 /> : <Save />}
        {savedFlash ? t("settings.saved") : t("settings.save")}
      </BlobButton>
      {!isDirty && (
        <p className="text-center text-xs text-muted-foreground">
          {t("settings.save_hint")}
        </p>
      )}
    </main>
  );
}
