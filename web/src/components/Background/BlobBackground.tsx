/**
 * Soft atmospheric wash used behind dense UI surfaces.
 * Intentionally minimal — primary motion lives in QuasarField.
 * Large, heavily blurred luminaires only (no geometric shapes).
 */
export const BlobBackground: React.FC = () => {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 overflow-hidden"
    >
      <div
        className="absolute -left-[20%] top-[-28%] h-[75%] w-[75%] rounded-full opacity-90"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(79, 114, 232, 0.12), transparent 70%)',
          filter: 'blur(52px)',
          animation: 'qp-aurora-a 52s cubic-bezier(0.4, 0, 0.2, 1) infinite alternate',
        }}
      />
      <div
        className="absolute -right-[14%] bottom-[-22%] h-[62%] w-[56%] rounded-full opacity-90"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(111, 79, 228, 0.09), transparent 72%)',
          filter: 'blur(60px)',
          animation: 'qp-aurora-b 68s cubic-bezier(0.4, 0, 0.2, 1) infinite alternate',
        }}
      />
      <div
        className="absolute left-[30%] top-[40%] h-[44%] w-[50%] rounded-full"
        style={{
          background:
            'radial-gradient(ellipse at center, rgba(14, 165, 233, 0.05), transparent 74%)',
          filter: 'blur(44px)',
        }}
      />
    </div>
  );
};
