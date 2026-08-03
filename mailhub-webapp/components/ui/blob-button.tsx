"use client";

import * as React from "react";
import { motion, useAnimationControls, type HTMLMotionProps } from "motion/react";
import type { VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

type BlobButtonProps = Omit<
  HTMLMotionProps<"button">,
  "animate" | "whileTap" | "onClick"
> &
  VariantProps<typeof buttonVariants> & {
    onClick?: React.MouseEventHandler<HTMLButtonElement>;
  };

/**
 * Primary-action button with a soft "blob" animation: a quick springy
 * squash-and-stretch on tap, like pressing a bubble.
 */
export function BlobButton({
  className,
  variant,
  size,
  onClick,
  children,
  ...props
}: BlobButtonProps) {
  const controls = useAnimationControls();

  const handleClick: React.MouseEventHandler<HTMLButtonElement> = (event) => {
    controls.start({
      scale: [1, 1.08, 0.94, 1],
      transition: {
        duration: 0.45,
        times: [0, 0.35, 0.7, 1],
        ease: "easeOut",
      },
    });
    onClick?.(event);
  };

  return (
    <motion.button
      className={cn(
        buttonVariants({ variant, size, className }),
        "will-change-transform",
      )}
      whileTap={{ scale: 0.94 }}
      animate={controls}
      onClick={handleClick}
      {...props}
    >
      {children}
    </motion.button>
  );
}
