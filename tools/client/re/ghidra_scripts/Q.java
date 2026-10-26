// Requetes en lot sur WoW.exe (Ghidra headless). Usage: -postScript Q.java <cmdfile> <outfile>
// Commandes (une par ligne): dec <va> | dis <va> <n> | xr <va> | str <sous-chaine> | callers <va> | fn <va>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.data.*;
import ghidra.program.model.mem.*;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public class Q extends GhidraScript {
  PrintWriter out; DecompInterface di;
  Address A(String s){ return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(Long.decode(s)); }
  public void run() throws Exception {
    String[] a = getScriptArgs();
    List<String> cmds = Files.readAllLines(Paths.get(a[0]));
    out = new PrintWriter(new FileWriter(a[1]));
    di = new DecompInterface(); di.openProgram(currentProgram);
    for (String c : cmds) {
      c = c.trim(); if (c.isEmpty() || c.startsWith("#")) continue;
      String[] p = c.split("\s+", 2);
      out.println("\n##### " + c);
      try {
        switch (p[0]) {
          case "dec": dec(A(p[1])); break;
          case "dis": { String[] q = p[1].split("\s+"); dis(A(q[0]), Integer.parseInt(q[1])); break; }
          case "xr": xr(A(p[1])); break;
          case "callers": callers(A(p[1])); break;
          case "str": str(p[1]); break;
          case "fn": fn(A(p[1])); break;
          case "imm": imm(Long.decode(p[1])); break;
          case "mk": { disassemble(A(p[1])); createFunction(A(p[1]), null); out.println("ok"); break; }
          default: out.println("?");
        }
      } catch (Exception e) { out.println("ERR " + e); }
      out.flush();
    }
    out.close();
  }
  void dec(Address ad) {
    Function f = getFunctionContaining(ad);
    if (f == null) { disassemble(ad); f = createFunction(ad, null); }
    if (f == null) { out.println("no function at " + ad); return; }
    out.println("// " + f.getName() + " @ " + f.getEntryPoint() + " size " + f.getBody().getNumAddresses());
    DecompileResults r = di.decompileFunction(f, 120, monitor);
    out.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "decomp fail " + r.getErrorMessage());
  }
  void dis(Address ad, int n) {
    Instruction i = getInstructionAt(ad); if (i == null) i = getInstructionContaining(ad);
    for (int k = 0; k < n && i != null; k++, i = i.getNext()) out.println(i.getAddress() + ": " + i);
  }
  void xr(Address ad) {
    for (Reference r : getReferencesTo(ad)) {
      Function f = getFunctionContaining(r.getFromAddress());
      out.println(r.getFromAddress() + " " + r.getReferenceType() + " in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()));
    }
  }
  void callers(Address ad) { xr(ad); }
  void imm(long v) {
    InstructionIterator it = currentProgram.getListing().getInstructions(true);
    while (it.hasNext()) {
      Instruction i = it.next();
      for (int k = 0; k < i.getNumOperands(); k++) {
        for (Object o : i.getOpObjects(k)) {
          if (o instanceof ghidra.program.model.scalar.Scalar && ((ghidra.program.model.scalar.Scalar) o).getUnsignedValue() == (v & 0xffffffffL)) {
            Function f = getFunctionContaining(i.getAddress());
            out.println(i.getAddress() + ": " + i + "  in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()));
          }
        }
      }
    }
  }
  void fn(Address ad) {
    Function f = getFunctionContaining(ad);
    if (f == null) { out.println("none"); return; }
    out.println(f.getName() + " entry " + f.getEntryPoint() + " body " + f.getBody().getMinAddress() + "-" + f.getBody().getMaxAddress());
  }
  void str(String sub) {
    DataIterator it = currentProgram.getListing().getDefinedData(true);
    while (it.hasNext()) {
      Data d = it.next();
      if (d.getValue() instanceof String) {
        String s = (String) d.getValue();
        if (s.contains(sub)) {
          out.println(d.getAddress() + " \"" + s.replace("\n","\n") + "\"");
          for (Reference r : getReferencesTo(d.getAddress())) {
            Function f = getFunctionContaining(r.getFromAddress());
            out.println("    xref " + r.getFromAddress() + " in " + (f == null ? "?" : f.getName() + "@" + f.getEntryPoint()));
          }
        }
      }
    }
  }
}
