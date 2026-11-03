'use client';

import { FormEvent, useEffect, useState } from 'react';
import { FileScan, ShieldCheck, Upload } from 'lucide-react';
import { PageHeading } from '@/components/ui';
import { api, ApiError, hasApiSession, type OCRCapture } from '@/lib/api';
import type { Supplier } from '@/types';

type InvoiceDraftLine = { description: string; quantity: string; unit_price: string };

export default function InvoiceCapturePage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [capture, setCapture] = useState<OCRCapture | null>(null);
  const [drafts, setDrafts] = useState<OCRCapture[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState('');
  const [supplierId, setSupplierId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [issuedDate, setIssuedDate] = useState('');
  const [subtotal, setSubtotal] = useState('');
  const [tax, setTax] = useState('');
  const [total, setTotal] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [items, setItems] = useState<InvoiceDraftLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    if (hasApiSession()) {
      void api.suppliers().then(setSuppliers).catch(e => setError(e instanceof Error ? e.message : 'Could not load suppliers.'));
      void api.invoiceCaptures().then(setDrafts).catch(e => setError(e instanceof Error ? e.message : 'Could not load invoice drafts.'));
    }
  }, []);
  useEffect(() => {
    if (!file) { setImagePreview(''); return; }
    const url = URL.createObjectURL(file);
    setImagePreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function process(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(''); setSuccess(''); setCapture(null);
    try {
      const result = await api.createInvoiceCapture(file);
      setDrafts(previous => [result, ...previous]);
      setCapture(result); setInvoiceNumber(result.draft.invoice_number); setIssuedDate(result.draft.issued_date);
      setSubtotal(result.draft.subtotal); setTax(result.draft.tax); setTotal(result.draft.total);
      setItems(result.draft.items);
      if (result.draft.currency) setCurrency(result.draft.currency);
      const match = suppliers.find(s => s.name.toLowerCase() === result.draft.supplier_name.toLowerCase());
      if (match) setSupplierId(match.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not read this invoice.');
    } finally { setBusy(false); }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!capture) return;
    setBusy(true); setError('');
    try {
      const result = await api.confirmInvoiceCapture(capture.id, {
        invoice_number: invoiceNumber, supplier_id: supplierId, subtotal, tax, total, currency,
        items: items.map(line => ({ ...line, description: line.description.trim() })),
        ...(issuedDate ? { issued_at: `${issuedDate}T12:00:00Z` } : {}),
      });
      setCapture(null); setFile(null);
      setDrafts(previous => previous.filter(draft => draft.id !== capture.id));
      setSuccess(`Invoice ${String(result.invoice_number)} has been saved for supplier review. No purchase or payment was created.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not confirm this invoice.');
    } finally { setBusy(false); }
  }

  async function rejectDraft() {
    if (!capture) return;
    setBusy(true); setError('');
    try {
      await api.rejectInvoiceCapture(capture.id);
      setCapture(null); setFile(null);
      setDrafts(previous => previous.filter(draft => draft.id !== capture.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reject this invoice draft.');
    } finally { setBusy(false); }
  }

  function updateLine(index: number, key: keyof InvoiceDraftLine, value: string) {
    setItems(previous => previous.map((line, i) => i === index ? { ...line, [key]: value } : line));
  }

  function resumeDraft(draft: OCRCapture) {
    setCapture(draft); setInvoiceNumber(draft.draft.invoice_number); setIssuedDate(draft.draft.issued_date);
    setSubtotal(draft.draft.subtotal); setTax(draft.draft.tax); setTotal(draft.draft.total);
    setCurrency(draft.draft.currency || 'USD'); setItems(draft.draft.items);
    const match = suppliers.find(s => s.name.toLowerCase() === draft.draft.supplier_name.toLowerCase());
    setSupplierId(match?.id ?? '');
  }

  return <>
    <PageHeading eyebrow="SUPPLIER DOCUMENTS" title="Invoice capture" description="Extract invoice details into a review draft. You confirm every field before an invoice record is created." action={<span className="ai-chip"><FileScan size={13}/> OCR requires review</span>}/>
    <div className="invoice-flow" aria-label="Invoice processing steps"><span>1 · Upload image</span><i/><span>2 · Review extracted fields</span><i/><span>3 · Confirm invoice record</span></div>
    {!capture && <form className="panel invoice-upload" onSubmit={process}>
      <div className="invoice-upload-icon"><Upload size={19}/></div><div><h2>Upload a supplier invoice</h2><p>JPEG, PNG, TIFF, or WebP · up to 10 MB. The image is processed for extraction and not retained in application storage.</p></div>
      <label className="file-picker">Choose invoice image<input type="file" accept="image/jpeg,image/png,image/tiff,image/webp" onChange={e => setFile(e.target.files?.[0] ?? null)}/></label>
      <span className="invoice-file-name">{file?.name ?? 'No image selected'}</span><button className="button button-primary" disabled={!file || busy || !hasApiSession()}>{busy ? 'Reading image…' : 'Extract fields'} <FileScan size={15}/></button>
      {!hasApiSession() && <p className="assistant-capability-note">Sign in with the API connection enabled to process real invoices. Preview mode does not fabricate OCR results.</p>}
    </form>}
    {!capture && drafts.length > 0 && <section className="panel invoice-draft-queue"><div><h2>Drafts waiting for review</h2><p>These OCR results have not been saved as invoices.</p></div>{drafts.map(draft => <article key={draft.id}><span><strong>{draft.draft.invoice_number || 'Invoice number not read'}</strong><small>{draft.draft.supplier_name || 'Supplier not identified'} · {Math.round(draft.draft.field_confidence * 100)}% field coverage</small></span><button className="button button-secondary" onClick={() => resumeDraft(draft)}>Continue review</button></article>)}</section>}
    {error && <div className="assistant-error" role="alert">{error}</div>}{success && <div className="invoice-success" role="status"><ShieldCheck size={17}/>{success}</div>}
    {capture && <section className="panel invoice-review">
      <div className="invoice-review-heading"><div><div className="eyebrow">REVIEW REQUIRED · NOT SAVED AS AN INVOICE</div><h2>Verify extracted details</h2><p>OCR can misread amounts and supplier names. Correct every field and verify the total before confirming.</p></div><span className="invoice-confidence">Field coverage {Math.round(capture.draft.field_confidence * 100)}%</span></div>
      <div className="invoice-ocr-meta"><span>Engine: {capture.ocr_engine}</span><span>Status: {capture.status}</span><span>All fields remain editable</span></div>
      {imagePreview && <figure className="invoice-source-image"><img src={imagePreview} alt="Uploaded supplier invoice for comparison with extracted fields"/><figcaption>Source image · shown from this browser session and not saved by the application</figcaption></figure>}
      <form onSubmit={confirm}>
        <div className="invoice-fields">
          <label>Supplier<select required value={supplierId} onChange={e => setSupplierId(e.target.value)}><option value="">Select supplier</option>{suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select><small>OCR read: {capture.draft.supplier_name || 'not identified'}</small></label>
          <label>Invoice number<input required value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)}/></label>
          <label>Invoice date<input type="date" value={issuedDate} onChange={e => setIssuedDate(e.target.value)}/></label>
          <label>Currency<input required maxLength={3} pattern="[A-Z]{3}" value={currency} onChange={e => setCurrency(e.target.value.toUpperCase())}/></label>
          <label>Subtotal<input required type="number" min="0" step="0.01" value={subtotal} onChange={e => setSubtotal(e.target.value)}/></label>
          <label>Tax<input required type="number" min="0" step="0.01" value={tax} onChange={e => setTax(e.target.value)}/></label>
          <label>Total<input required type="number" min="0" step="0.01" value={total} onChange={e => setTotal(e.target.value)}/></label>
        </div>
        <div className="invoice-extracted"><div className="invoice-lines-heading"><strong>Extracted line items · verify against source image</strong><button type="button" className="button button-secondary" onClick={() => setItems(previous => [...previous, { description: '', quantity: '1', unit_price: '0.00' }])}>Add line</button></div>
          {items.length ? <div className="invoice-edit-lines">{items.map((item, i) => <div className="invoice-edit-line" key={i}><label>Description<input required value={item.description} onChange={e => updateLine(i, 'description', e.target.value)}/></label><label>Quantity<input required type="number" min="0.001" step="0.001" value={item.quantity} onChange={e => updateLine(i, 'quantity', e.target.value)}/></label><label>Unit price<input required type="number" min="0" step="0.01" value={item.unit_price} onChange={e => updateLine(i, 'unit_price', e.target.value)}/></label><button type="button" className="icon-button" aria-label={`Remove invoice line ${i + 1}`} onClick={() => setItems(previous => previous.filter((_, index) => index !== i))}>×</button></div>)}</div> : <p>No line items were confidently extracted. Add verified lines or confirm the totals only.</p>}
          <details><summary>Show OCR text for comparison</summary><pre>{capture.raw_text}</pre></details>
        </div>
        <div className="invoice-confirm-note"><ShieldCheck size={16}/><span>Confirmation creates a supplier invoice record and audit entry. It does not record a purchase, pay the supplier, or update inventory.</span></div>
        <div className="invoice-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={() => void rejectDraft()}>Reject draft</button><button className="button button-primary" disabled={busy || !supplierId || !hasApiSession()}>{busy ? 'Saving confirmed invoice…' : 'Confirm invoice record'}</button></div>
      </form>
    </section>}
  </>;
}
