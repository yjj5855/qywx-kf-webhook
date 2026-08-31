import {X} from 'lucide-react';
import {ReactNode} from 'react';

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  widthClass?: string;
}

export default function Modal({title, onClose, children, widthClass = 'max-w-lg'}: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 px-4 py-12 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`w-full ${widthClass} rounded-2xl bg-white shadow-xl`}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 className="text-base font-bold text-slate-800">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            aria-label="关闭"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="px-5 py-5">{children}</div>
      </div>
    </div>
  );
}
