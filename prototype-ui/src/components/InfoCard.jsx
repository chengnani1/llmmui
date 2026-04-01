export default function InfoCard({ title, children, extra }) {
  return (
    <section className="panel p-6">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="section-title">{title}</h3>
        {extra}
      </div>
      {children}
    </section>
  );
}
