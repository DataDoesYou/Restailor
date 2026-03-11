"use client";
import * as React from "react";
import * as ToastPrimitives from "@radix-ui/react-toast";
import { cn } from "@/lib/utils";

export const ToastProvider = ToastPrimitives.Provider;
export const ToastViewport = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Viewport>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Viewport>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Viewport
    ref={ref}
    className={cn(
      "fixed top-0 right-0 z-50 m-4 flex max-h-screen w-full max-w-sm flex-col gap-2",
      className
    )}
    {...props}
  />
));
ToastViewport.displayName = ToastPrimitives.Viewport.displayName;

export const Toast = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof ToastPrimitives.Root>) => (
  <ToastPrimitives.Root className={cn("rounded-md border bg-white p-3 shadow", className)} {...props} />
);

export const ToastTitle = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof ToastPrimitives.Title>) => (
  <ToastPrimitives.Title className={cn("text-sm font-medium", className)} {...props} />
);

export const ToastDescription = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof ToastPrimitives.Description>) => (
  <ToastPrimitives.Description className={cn("text-sm text-muted-foreground", className)} {...props} />
);
