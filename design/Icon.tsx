import type { CSSProperties } from 'react';
import { ICON_PATHS } from './iconPaths';
import type { IconName } from './iconPaths';

export type { IconName };

interface IconProps {
  name: IconName;
  /** Pixel size. Defaults to the surrounding `--icon-size` (or 1em). */
  size?: number;
  className?: string;
  /** Accessible label. Omit for decorative icons next to visible text. */
  label?: string;
}

/**
 * The single icon component for Open Prism. One outline family on a 24px grid,
 * 1.75 stroke, `currentColor`. Never use emoji or text glyphs as icons.
 */
export function Icon({ name, size, className = '', label }: IconProps) {
  const style = size ? ({ '--icon-size': `${size}px` } as CSSProperties) : undefined;
  return (
    <svg
      className={`op-icon ${className}`.trim()}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      // Static, trusted markup from iconPaths.ts
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] }}
    />
  );
}
