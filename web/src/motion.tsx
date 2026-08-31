import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * 动效规格（对齐 motionsites 五层结构化提示词的方法论，克制企业风）：
 * - 入场：y+14px 位移 + 淡入，420ms，easeOut [0.22, 1, 0.36, 1]，级联间隔 70ms
 * - 滚动渐显：进入视口 15% 触发，同参数，只播一次
 * - 微交互：卡片 hover 上浮 2px + 阴影加深，180ms
 * - 全部尊重 prefers-reduced-motion（降级为无位移直接显示）
 */

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

export function FadeIn({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.42, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}

export function FadeInOnScroll({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.48, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}

/** 首屏主标题：渐层文字 + 级联入场 */
export function HeroTitle({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <motion.h1
      className="hero-gradient-text"
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: EASE, delay: 0.08 }}
    >
      {children}
    </motion.h1>
  );
}

/** 微交互卡片：hover 上浮 2px + 阴影 */
export function LiftCard({ children, className }: { children: ReactNode; className?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      whileHover={reduced ? undefined : { y: -2, boxShadow: "0 10px 28px rgba(15, 23, 42, .10)" }}
      transition={{ duration: 0.18, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
