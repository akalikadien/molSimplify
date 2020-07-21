# @file mol3D.py
#  Defines mol3D class and contains useful manipulation/retrieval routines.
#
#  Written by Tim Ioannidis and JP Janet for HJK Group
#
#  Dpt of Chemical Engineering, MIT

import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from math import sqrt
import numpy as np
import openbabel

from molSimplify.Classes.atom3D import atom3D
from molSimplify.Classes.globalvars import globalvars
from molSimplify.Scripts.geometry import distance, connectivity_match, vecangle, rotation_params, rotate_around_axis
from molSimplify.Scripts.rmsd import rigorous_rmsd

try:
    import PyQt5
    from molSimplify.Classes.miniGUI import *

    # PyQt5 flag
    qtflag = True
except ImportError:
    qtflag = False
    pass


# Euclidean distance between points
#  @param R1 Point 1
#  @param R2 Point 2
#  @return Euclidean distance
def distance(R1, R2):
    dx = R1[0] - R2[0]
    dy = R1[1] - R2[1]
    dz = R1[2] - R2[2]
    d = sqrt(dx ** 2 + dy ** 2 + dz ** 2)
    return d


# Wrapper for executing bash commands
#  @param cmd Command to be executed
#  @return Stdout
def mybash(cmd):
    p = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout = []
    while True:
        line = p.stdout.readline()
        stdout.append(line)
        if line == '' and p.poll() != None:
            break
    return ''.join(stdout)


# Class for molecules that will be used to manipulate coordinates and other properties
class mol3D:
    # Constructor
    #  @param self The object pointer
    def __init__(self, use_atom_specific_cutoffs=False):
        # List of atom3D objects
        self.atoms = []
        # Number of atoms
        self.natoms = 0
        # Mass of molecule
        self.mass = 0
        # Size of molecule
        self.size = 0
        # Charge of molecule
        self.charge = 0
        # Force field optimization settings
        self.ffopt = 'BA'
        # Name of molecule
        self.name = ''
        # Holder for openbabel molecule
        self.OBMol = False
        # Holder for bond order matrix
        self.BO_mat = False
        # Holder for bond order dictionary
        self.bo_dict = False
        # List of connection atoms
        self.cat = []
        # Denticity
        self.denticity = 0
        # Identifier
        self.ident = ''
        # Holder for global variables
        self.globs = globalvars()
        # Holder for molecular graph
        self.graph = []
        self.xyzfile = 'undef'
        self.updated = False
        self.needsconformer = False
        # Holder for molecular group
        self.grps = False
        # Holder rfor metals
        self.metals = False

        # Holder for partial charge for each atom
        self.partialcharges = []

        # ---geo_check------
        self.dict_oct_check_loose = self.globs.geo_check_dictionary()[
            "dict_oct_check_loose"]
        self.dict_oct_check_st = self.globs.geo_check_dictionary()[
            "dict_oct_check_st"]
        self.dict_oneempty_check_loose = self.globs.geo_check_dictionary()[
            "dict_oneempty_check_loose"]
        self.dict_oneempty_check_st = self.globs.geo_check_dictionary()[
            "dict_oneempty_check_st"]
        self.oct_angle_ref = self.globs.geo_check_dictionary()["oct_angle_ref"]
        self.oneempty_angle_ref = self.globs.geo_check_dictionary()[
            "oneempty_angle_ref"]
        self.geo_dict = dict()
        self.std_not_use = list()

        self.num_coord_metal = -1
        self.catoms = list()
        self.init_mol_trunc = False
        self.my_mol_trunc = False
        self.flag_oct = -1
        self.flag_list = list()
        self.dict_lig_distort = dict()
        self.dict_catoms_shape = dict()
        self.dict_orientation = dict()
        self.dict_angle_linear = dict()
        self.use_atom_specific_cutoffs = use_atom_specific_cutoffs

    # Performs angle centric manipulation
    #
    #  A submolecule is rotated about idx2.
    #
    #  @param self The object pointer
    #  @param idx1 Index of bonded atom containing submolecule to be moved
    #  @param idx2 Index of anchor atom
    #  @param idx3 Index of anchor atom
    #  @param angle New bond angle in degree
    def ACM(self, idx1, idx2, idx3, angle):
        atidxs_to_move = self.findsubMol(idx1, idx2)
        atidxs_anchor = self.findsubMol(idx2, idx1)
        submol_to_move = mol3D()
        submol_anchor = mol3D()
        for atidx in atidxs_to_move:
            atom = self.getAtom(atidx)
            submol_to_move.addAtom(atom)
        for atidx in atidxs_anchor:
            atom = self.getAtom(atidx)
            submol_anchor.addAtom(atom)
        mol = mol3D()
        mol.copymol3D(submol_anchor)
        r0 = self.getAtom(idx1).coords()
        r1 = self.getAtom(idx2).coords()
        r2 = self.getAtom(idx3).coords()
        theta, u = rotation_params(r2, r1, r0)
        if theta < 90:
            angle = 180 - angle
        submol_to_move = rotate_around_axis(
            submol_to_move, r1, u, theta - angle)
        # print('atidxs_to_move are ' + str(atidxs_to_move))
        for i, atidx in enumerate(atidxs_to_move):
            asym = self.atoms[atidx].sym
            xyz = submol_to_move.getAtomCoords(i)
            self.atoms[atidx].__init__(Sym=asym, xyz=xyz)
        # mol.copymol3D(submol_to_move)
        # self.deleteatoms(range(self.natoms))
        # self.copymol3D(mol)

    # Performs angle centric manipulation alnog a given axis
    #
    #  A submolecule is rotated about idx2.
    #
    #  @param self The object pointer
    #  @param idx1 Index of bonded atom containing submolecule to be moved
    #  @param idx2 Index of anchor atom
    #  @param u axis of rotation
    #  @param angle New bond angle in degree
    def ACM_axis(self, idx1, idx2, u, angle):
        atidxs_to_move = self.findsubMol(idx1, idx2)
        atidxs_anchor = self.findsubMol(idx2, idx1)
        submol_to_move = mol3D()
        submol_anchor = mol3D()
        for atidx in atidxs_to_move:
            atom = self.getAtom(atidx)
            submol_to_move.addAtom(atom)
        for atidx in atidxs_anchor:
            atom = self.getAtom(atidx)
            submol_anchor.addAtom(atom)
        mol = mol3D()
        mol.copymol3D(submol_anchor)
        r0 = self.getAtom(idx1).coords()
        r1 = self.getAtom(idx2).coords()
        submol_to_move = rotate_around_axis(submol_to_move, r1, u, angle)
        # print('atidxs_to_move are ' + str(atidxs_to_move))
        for i, atidx in enumerate(atidxs_to_move):
            asym = self.atoms[atidx].sym
            xyz = submol_to_move.getAtomCoords(i)
            self.atoms[atidx].__init__(Sym=asym, xyz=xyz)
        # mol.copymol3D(submol_to_move)
        # self.deleteatoms(range(self.natoms))
        # self.copymol3D(mol)

    # Add atom to molecule
    #
    #  Added atom is appended to the end of the list.
    #  @param self The object pointer
    #  @param atom atom3D of atom to be added
    def addAtom(self, atom, index=None, auto_populate_BO_dict=True):
        if index == None:
            index = len(self.atoms)
        # self.atoms.append(atom)
        self.atoms.insert(index, atom)
        # If partial charge list exists, add partial charge:
        if len(self.partialcharges) == self.natoms:
            partialcharge = atom.partialcharge
            if partialcharge == None:
                partialcharge = 0.0
            self.partialcharges.insert(index, partialcharge)
        if atom.frozen:
            self.atoms[index].frozen = True

        # If bo_dict exists, auto-populate the bo_dict with "1"
        # for all newly bonded atoms. (Atoms indices in pair must be  sorted,
        # i.e. a bond order pair (1,5) is valid  but (5,1) is invalid.
        if auto_populate_BO_dict and self.bo_dict:
            new_bo_dict = {}
            # Adjust indices in bo_dict to reflect insertion
            for pair, order in self.bo_dict.items():
                idx1, idx2 = pair
                if idx1 >= index:
                    idx1 += 1
                if idx2 >= index:
                    idx2 += 1
                new_bo_dict[(idx1, idx2)] = order
            self.bo_dict = new_bo_dict

            # Adjust indices in graph to reflect insertion
            self.graph = np.array(self.graph)  # cast graph as numpy array
            graph_size = self.graph.shape[0]
            self.graph = np.insert(
                self.graph, index, np.zeros(graph_size), axis=0)
            self.graph = np.insert(
                self.graph, index, np.zeros(graph_size+1), axis=1)

            # Grab connecting atom indices and populate bo_dict and graph
            catom_idxs = self.getBondedAtoms(index)
            for catom_idx in catom_idxs:
                sorted_indices = sorted([catom_idx, index])
                self.bo_dict[tuple(sorted_indices)] = '1'
                self.graph[catom_idx, index] = 1
                self.graph[index, catom_idx] = 1
        else:
            self.graph = []

        self.natoms += 1
        self.mass += atom.mass
        self.size = self.molsize()
        self.metal = False

    # Change type of atom in molecule
    #
    #  @param self The object pointer
    #  @param atom_ind int index of atom
    #  @param atom_type str type of the new atom
    def changeAtomtype(self, atom_ind, atom_type):
        self.atoms[atom_ind].sym = atom_type
        self.metal = False

    # Aligns two molecules such that the coordinates of two atoms overlap.
    #
    #  Second molecules is translated relative to the first.
    #  No rotations are performed here. Use other functions for rotations.
    #  @param self The object pointer
    #  @param atom1 atom3D of reference atom in first molecule (not translated)
    #  @param atom2 atom3D of reference atom in second molecule (translated)
    def alignmol(self, atom1, atom2):
        # get distance vector between atoms 1,2
        dv = atom2.distancev(atom1)
        self.translate(dv)

    # Performs bond centric manipulation (same as Avogadro, stretching/squeezing bonds)
    #
    #  A submolecule is translated along the bond axis connecting it to an anchor atom.
    #
    #  Illustration: H3A-BH3 -> H3A----BH3 where B = idx1 and A = idx2
    #  @param self The object pointer
    #  @param idx1 Index of bonded atom containing submolecule to be moved
    #  @param idx2 Index of anchor atom
    #  @param d New bond length in Angstroms
    def BCM(self, idx1, idx2, d):
        bondv = self.getAtom(idx1).distancev(self.getAtom(idx2))  # 1 - 2
        # compute current bond length
        u = 0.0
        for u0 in bondv:
            u += (u0 * u0)
        u = sqrt(u)
        dl = d - u  # dl > 0: stretch, dl < 0: shrink
        dR = [i * (d / u - 1) for i in bondv]
        submolidxes = self.findsubMol(idx1, idx2)
        for submolidx in submolidxes:
            self.getAtom(submolidx).translate(dR)
        # for i in self.getBondedAtoms(idx1):
        #     if i != idx2:
        #         self.getAtom(i).translate(dR)
        # self.getAtom(idx1).translate(dR)

    # Performs bond centric manipulation (same as Avogadro, stretching/squeezing bonds)
    #
    #  A submolecule is translated along the bond axis connecting it to an anchor atom.
    #
    #  Illustration: H3A-BH3 -> H3A----BH3 where B = idx1 and A = idx2
    #  @param self The object pointer
    #  @param idx1 Index of bonded atom containing submolecule to be moved
    #  @param idx2 Index of anchor atom
    #  @param d New bond length in Angstroms
    def BCM_opt(self, idx1, idx2, d):
        self.convert2OBMol()
        OBMol = self.OBMol
        ff = openbabel.OBForceField.FindForceField('mmff94')
        constr = openbabel.OBFFConstraints()
        constr.AddDistanceConstraint(idx1 + 1, idx2 + 1, d)
        s = ff.Setup(OBMol, constr)
        if s is not True:
            print('forcefield setup failed.')
            exit()
        else:
            ff.SteepestDescent(500)
            ff.GetCoordinates(OBMol)
        self.OBMol = OBMol
        self.convert2mol3D()

    # Computes coordinates of center of mass of molecule
    #  @param self The object pointer
    #  @return List of center of mass coordinates
    def centermass(self):
        # OUTPUT
        #   - pcm: vector representing center of mass
        # initialize center of mass and mol mass
        pmc = [0, 0, 0]
        mmass = 0
        # loop over atoms in molecule
        if self.natoms > 0:
            for atom in self.atoms:
                # calculate center of mass (relative weight according to atomic mass)
                xyz = atom.coords()
                pmc[0] += xyz[0] * atom.mass
                pmc[1] += xyz[1] * atom.mass
                pmc[2] += xyz[2] * atom.mass
                mmass += atom.mass
            # normalize
            pmc[0] /= mmass
            pmc[1] /= mmass
            pmc[2] /= mmass
        else:
            pmc = False
            print(
                'ERROR: Center of mass calculation failed. Structure will be inaccurate.\n')
        return pmc

    # Computes coordinates of center of symmetry of molecule
    #
    #  Identical to centermass, but not weighted by atomic masses.
    #  @param self The object pointer
    #  @return List of center of symmetry coordinates
    def centersym(self):
        # initialize center of mass and mol mass
        pmc = [0, 0, 0]
        # loop over atoms in molecule
        for atom in self.atoms:
            # calculate center of symmetry
            xyz = atom.coords()
            pmc[0] += xyz[0]
            pmc[1] += xyz[1]
            pmc[2] += xyz[2]
        # normalize
        pmc[0] /= self.natoms
        pmc[1] /= self.natoms
        pmc[2] /= self.natoms
        return pmc

    # remove all openbabel bond order indo
    #  @param self The object pointer
    def cleanBonds(self):
        obiter = openbabel.OBMolBondIter(self.OBMol)
        n = self.natoms
        bonds_to_del = []
        for bond in obiter:
            these_inds = [bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()]
            bonds_to_del.append(bond)
        for i in bonds_to_del:
            self.OBMol.DeleteBond(i)

    # Converts OBMol to mol3D
    #
    #  Generally used after openbabel operations, such as when initializing a molecule from a file or FF optimizing it.
    #  @param self The object pointer
    def convert2mol3D(self):
        # initialize again
        self.initialize()
        # get elements dictionary
        elem = globalvars().elementsbynum()
        # loop over atoms
        for atom in openbabel.OBMolAtomIter(self.OBMol):
            # get coordinates
            pos = [atom.GetX(), atom.GetY(), atom.GetZ()]
            # get atomic symbol
            sym = elem[atom.GetAtomicNum() - 1]
            # add atom to molecule
            self.addAtom(atom3D(sym, [pos[0], pos[1], pos[2]]))
        # reset metal ID
        self.metal = False

    # Converts mol3D to OBMol
    #
    #  Required for performing openbabel operations on a molecule, such as FF optimizations.
    #  @param self The object pointer
    #  @param force_clean bool force no bond info retention
    #  @param ignoreX bool skip "X" atoms in mol3D conversion
    def convert2OBMol(self, force_clean=False, ignoreX=False):
        # get BO matrix if exits:
        repop = False

        if not (self.OBMol == False) and not force_clean:
            BO_mat = self.populateBOMatrix()

            repop = True
        elif not (self.BO_mat == False) and not force_clean:
            BO_mat = self.BO_mat
            repop = True
            # write temp xyz
        fd, tempf = tempfile.mkstemp(suffix=".xyz")
        os.close(fd)
        #self.writexyz('tempr.xyz', symbsonly=True)
        self.writexyz(tempf, symbsonly=True, ignoreX=ignoreX)

        obConversion = openbabel.OBConversion()
        obConversion.SetInFormat("xyz")

        OBMol = openbabel.OBMol()
        obConversion.ReadFile(OBMol, tempf)

        self.OBMol = []
        self.OBMol = OBMol

        os.remove(tempf)

        if repop and not force_clean:
            self.cleanBonds()
            for i in range(0, self.natoms):
                for j in range(0, self.natoms):
                    if BO_mat[i][j] > 0:
                        self.OBMol.AddBond(i + 1, j + 1, int(BO_mat[i][j]))

    # Converts mol3D to OBMol through mol2 function.
    #
    #  Required for performing openbabel operations on a molecule, such as FF optimizations.
    #  @param self The object pointer
    #  @param force_clean bool force no bond info retention
    #  @param ignoreX bool skip "X" atoms in mol3D conversion
    def convert2OBMol2(self, force_clean=False, ignoreX=False):
        # get BO matrix if exits:
        obConversion = openbabel.OBConversion()
        obConversion.SetInFormat('mol2')
        if not len(self.graph):
            self.createMolecularGraph()
        if not self.bo_dict:  # If bonddict not assigned - Use OBMol to perceive bond orders
            mol2string = self.writemol2('temporary', writestring=True,
                                        ignoreX=ignoreX, force=True)
            OBMol = openbabel.OBMol()
            obConversion.ReadString(OBMol, mol2string)
            OBMol.PerceiveBondOrders()
            #####
            obConversion.SetOutFormat('mol2')
            ss = obConversion.WriteString(OBMol)
            # Update atom types from OBMol
            lines = ss.split('ATOM\n')[1].split(
                '@<TRIPOS>BOND')[0].split('\n')[:-1]
            for i, line in enumerate(lines):
                if '.' in line.split()[5]:
                    self.atoms[i].name = line.split()[5].split('.')[1]
            ######
            self.OBMol = []
            self.OBMol = OBMol
            BO_mat = self.populateBOMatrix(bonddict=True)
            self.BO_mat = BO_mat
        else:
            mol2string = self.writemol2('temporary', writestring=True,
                                        ignoreX=ignoreX)
            OBMol = openbabel.OBMol()
            obConversion.ReadString(OBMol, mol2string)
            self.OBMol = []
            self.OBMol = OBMol
            BO_mat = self.populateBOMatrix(bonddict=False)
            self.BO_mat = BO_mat

    def resetBondOBMol(self):
        if self.OBMol:
            BO_mat = self.populateBOMatrix()
            self.cleanBonds()
            for i in range(0, self.natoms):
                for j in range(0, self.natoms):
                    if BO_mat[i][j] > 0:
                        self.OBMol.AddBond(i + 1, j + 1, int(BO_mat[i][j]))
        else:
            print("OBmol does not exist")

    # Combines two molecules
    #
    #  Each atom in the second molecule is appended to the first while preserving orders.
    #  @param self The object pointer
    #  @param mol mol3D containing molecule to be added
    #  @param list of tuples (ind1,ind2,order) bonds to add (optional)
    #  @param dirty bool set to true for straight addition, not bond safe
    #  @return mol3D contaning combined molecule
    # def combine(self,mol):
    #    cmol = self
    #    n_one = cmol.natoms
    #    n_two = mol.natoms
    #    for atom in mol.atoms:
    #        cmol.addAtom(atom)
    #    cmol.graph = []
    #    return cmol

    def combine(self, mol, bond_to_add=[], dirty=False):
        cmol = self

        if not dirty:
            # BondSafe
            cmol.convert2OBMol(force_clean=False, ignoreX=True)
            mol.convert2OBMol(force_clean=False, ignoreX=True)
            n_one = cmol.natoms
            n_two = mol.natoms
            n_tot = n_one + n_two
            # allocate
            jointBOMat = np.zeros([n_tot, n_tot])
            # get individual mats
            con_mat_one = cmol.populateBOMatrix()
            con_mat_two = mol.populateBOMatrix()
            # combine mats
            for i in range(0, n_one):
                for j in range(0, n_one):
                    jointBOMat[i][j] = con_mat_one[i][j]
            for i in range(0, n_two):
                for j in range(0, n_two):
                    jointBOMat[i + n_one][j + n_one] = con_mat_two[i][j]
            # optional add additional bond(s)
            if bond_to_add:
                for bond_tuples in bond_to_add:
                    # print('adding bond ' + str(bond_tuples))
                    jointBOMat[bond_tuples[0], bond_tuples[1]] = bond_tuples[2]
                    jointBOMat[bond_tuples[1], bond_tuples[0]] = bond_tuples[2]
                    # jointBOMat[bond_tuples[0], bond_tuples[1]+n_one] = bond_tuples[2]
                    # jointBOMat[bond_tuples[1]+n_one, bond_tuples[0]] = bond_tuples[2]

        # add mol3Ds
        for atom in mol.atoms:
            cmol.addAtom(atom)
        if not dirty:
            cmol.convert2OBMol(ignoreX=True)
            # clean all bonds
            cmol.cleanBonds()
            # restore bond info
            for i in range(0, n_tot):
                for j in range(0, n_tot):
                    if jointBOMat[i][j] > 0:
                        cmol.OBMol.AddBond(i + 1, j + 1, int(jointBOMat[i][j]))
        # reset graph
        cmol.graph = []
        self.metal = False
        return cmol

    # Prints coordinates of all atoms in molecule
    #  @param self The object pointer
    #  @return String containing coordinates
    def coords(self):
        # OUTPUT
        #   - atom: string with xyz-style coordinates
        ss = ''  # initialize returning string
        ss += "%d \n\n" % self.natoms
        for atom in self.atoms:
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])
        return ss

    # Returns coordinates of all atoms in molecule as a list of lists
    #  @param self The object pointer
    #  @return List of all atoms in molecule
    def coordsvect(self):
        ss = []
        for atom in self.atoms:
            xyz = atom.coords()
            ss.append(xyz)
        return np.array(ss)

    def symvect(self):
        ss = []
        for atom in self.atoms:
            ss.append(atom.sym)
        return np.array(ss)

    def typevect(self):
        ss = []
        for atom in self.atoms:
            ss.append(atom.name)
        return np.array(ss)

    # Copies properties and atoms of another existing mol3D object into current mol3D object.
    #
    #  WARNING: NEVER EVER USE mol3D = mol0 to do this. It doesn't work.
    #
    #  WARNING: ONLY USE ON A FRESH INSTANCE OF MOL3D.
    #  @param self The object pointer
    #  @param mol0 mol3D of molecule to be copied
    def copymol3D(self, mol0):
        # copy atoms
        for i, atom0 in enumerate(mol0.atoms):
            self.addAtom(atom3D(atom0.sym, atom0.coords(), atom0.name))
            if atom0.frozen:
                self.getAtom(i).frozen = True
        # copy other attributes
        self.cat = mol0.cat
        self.charge = mol0.charge
        self.denticity = mol0.denticity
        self.ident = mol0.ident
        self.ffopt = mol0.ffopt
        self.OBMol = mol0.OBMol
        self.name = mol0.name
        self.graph = mol0.graph
        self.bo_dict = mol0.bo_dict
        self.use_atom_specific_cutoffs = mol0.use_atom_specific_cutoffs

    # Create molecular graph (connectivity matrix) from mol3D info
    #  @param self The object pointer
    #  @oct flag to control  special oct-metal bonds
    def createMolecularGraph(self, oct=True):
        if not len(self.graph):
            index_set = list(range(0, self.natoms))
            A = np.zeros((self.natoms, self.natoms))
            catoms_metal = list()
            metal_ind = None
            for i in index_set:
                if oct:
                    if self.getAtom(i).ismetal():
                        this_bonded_atoms = self.get_fcs()
                        metal_ind = i
                        catoms_metal = this_bonded_atoms
                        if i in this_bonded_atoms:
                            this_bonded_atoms.remove(i)
                    else:
                        this_bonded_atoms = self.getBondedAtomsOct(i, debug=False,
                                                                   atom_specific_cutoffs=self.use_atom_specific_cutoffs)
                else:
                    this_bonded_atoms = self.getBondedAtoms(i, debug=False)
                for j in index_set:
                    if j in this_bonded_atoms:
                        A[i, j] = 1
            if not metal_ind == None:
                for i in index_set:
                    if not i in catoms_metal:
                        A[i, metal_ind] = 0
                        A[metal_ind, i] = 0
            self.graph = A

    # Deletes specific atom from molecule
    #
    #  Also updates mass and number of atoms, and recreates the molecular graph.
    #  @param self The object pointer
    #  @param atomIdx Index of atom to be deleted
    def deleteatom(self, atomIdx):
        if atomIdx < 0:
            atomIdx = self.natoms + atomIdx
        if atomIdx >= self.natoms:
            raise Exception('mol3D object cannot delete atom '+str(atomIdx) +
                            ' because it only has '+str(self.natoms)+' atoms!')
        if self.bo_dict:
            self.convert2OBMol2()
            save_inds = [x for x in range(self.natoms) if x != atomIdx]
            save_bo_dict = self.get_bo_dict_from_inds(save_inds)
            self.bo_dict = save_bo_dict
        else:
            self.convert2OBMol()
        self.OBMol.DeleteAtom(self.OBMol.GetAtom(atomIdx + 1))
        self.mass -= self.getAtom(atomIdx).mass
        self.natoms -= 1
        if len(self.graph):
            self.graph = np.delete(
                np.delete(self.graph, atomIdx, 0), atomIdx, 1)
        self.metal = False
        del (self.atoms[atomIdx])

    # Freezes specific atom in molecule
    #
    #  This is for the FF optimization settings.
    #  @param self The object pointer
    #  @param atomIdx Index of atom to be frozen
    def freezeatom(self, atomIdx):
        # INPUT
        #   - atomIdx: index of atom to be frozen
        self.atoms[atomIdx].frozen = True

    # Deletes list of atoms from molecule
    #
    #  Loops over deleteatom, starting from the largest index so ordering is preserved.
    #  @param self The object pointer
    #  @param Alist List of atom indices to be deleted
    def deleteatoms(self, Alist):
        for i in Alist:
            if i > self.natoms:
                raise Exception('mol3D object cannot delete atom '+str(i) +
                                ' because it only has '+str(self.natoms)+' atoms!')
        # convert negative indexes to positive indexes
        Alist = [self.natoms+i if i < 0 else i for i in Alist]
        if self.bo_dict:
            self.convert2OBMol2()
            save_inds = [x for x in range(self.natoms) if x not in Alist]
            save_bo_dict = self.get_bo_dict_from_inds(save_inds)
            self.bo_dict = save_bo_dict
        else:
            self.convert2OBMol()
        for h in sorted(Alist, reverse=True):
            self.OBMol.DeleteAtom(self.OBMol.GetAtom(int(h) + 1))
            self.mass -= self.getAtom(h).mass
            self.natoms -= 1
            del (self.atoms[h])
        if len(self.graph):
            self.graph = np.delete(np.delete(self.graph, Alist, 0), Alist, 1)
        self.metal = False

    # Freezes list of atoms in molecule
    #
    #  Loops over freezeatom(), starting from the largest index so ordering is preserved.
    #  @param self The object pointer
    #  @param Alist List of atom indices to be frozen
    def freezeatoms(self, Alist):
        # INPUT
        #   - Alist: list of atoms to be frozen
        for h in sorted(Alist, reverse=True):
            self.freezeatom(h)

    # Get ligand mol without hydrogens
    #
    # Loops over the atoms and makes a submol that contains
    # all of the atoms without the hydrogens:
    def get_submol_noHs(self):
        keep_list = []
        for i in range(self.natoms):
            if self.getAtom(i).symbol() == 'H':
                continue
            else:
                keep_list.append(i)
        mol_noHs = self.create_mol_with_inds(keep_list)
        return mol_noHs

    # Deletes all hydrogens from molecule.
    #
    #  Calls deleteatoms, so ordering of heavy atoms is preserved.
    #  @param self The object pointer
    def deleteHs(self):
        # metalind = self.findMetal()[0]
        # metalcons = self.getBondedAtoms(metalind)
        hlist = []
        for i in range(self.natoms):
            if self.getAtom(i).sym == 'H':  # and i not in metalcons:
                hlist.append(i)
        self.deleteatoms(hlist)

    # Gets distance between centers of mass of two molecules
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @return Center of mass distance
    def distance(self, mol):
        # INPUT
        #   - mol: second molecule
        # OUTPUT
        #   - pcm: distance between centers of mass
        cm0 = self.centermass()
        cm1 = mol.centermass()
        pmc = distance(cm0, cm1)
        return pmc

    # Creates and saves an svg file of the molecule
    #
    #  Also renders it in a fake gui window if PyQt5 is installed.
    #  Copied from mGUI function.
    #  @param self The object pointer
    #  @param filename Name of svg file
    def draw_svg(self, filename):
        obConversion = openbabel.OBConversion()
        obConversion.SetOutFormat("svg")
        obConversion.AddOption("i", obConversion.OUTOPTIONS, "")
        # return the svg with atom labels as a string
        svgstr = obConversion.WriteString(self.OBMol)
        namespace = "http://www.w3.org/2000/svg"
        ET.register_namespace("", namespace)
        tree = ET.fromstring(svgstr)
        svg = tree.find("{{{ns}}}g/{{{ns}}}svg".format(ns=namespace))
        newsvg = ET.tostring(svg).decode("utf-8")
        # write unpacked svg file
        fname = filename + '.svg'
        with open(fname, "w") as svg_file:
            svg_file.write(newsvg)
        if qtflag:
            # Initialize fake gui
            fakegui = miniGUI(sys.argv)
            # Add the svg to the window
            fakegui.addsvg(fname)
            # Show window
            fakegui.show()
        else:
            print('No PyQt5 found. SVG file written to directory.')

    # Applies an ffopt on the mol3D 
    #  @param self The object pointer
    #  @param constraints --> list of atoms to be frozen in place
    #  @return en --> energy of forcefield optimization. ffopt applies on molecule itself.
    def apply_ffopt(self, constraints = False):
        forcefield = openbabel.OBForceField.FindForceField('uff')
        constr = openbabel.OBFFConstraints()
        if constraints:
            for catom in range(constraints):
                # Openbabel uses a 1 index instead of a 0 index.
                constr.AddAtomConstraint(catom+1) 
        self.convert2OBMol()
        forcefield.Setup(self.OBMol,constr)
        if self.OBMol.NumHvyAtoms() > 10:
            forcefield.ConjugateGradients(200)
        else:
            forcefield.ConjugateGradients(50)
        forcefield.GetCoordinates(self.OBMol)
        en = forcefield.Energy()
        self.convert2mol3D()
        return en

    # Finds closest metal atom to a given atom
    #  @param self The object pointer
    #  @param atom0 Index of reference atom
    #  @return Index of closest metal atom
    def findcloseMetal(self, atom0):
        if not self.metals:
            self.findMetal()

        mm = False
        mindist = 1000
        for i in enumerate(self.metals):
            atom = self.getAtom(i)
            if distance(atom.coords(), atom0.coords()) < mindist:
                mindist = distance(atom.coords(), atom0.coords())
                mm = i
        # if no metal, find heaviest atom
        if not mm:
            maxaw = 0
            for i, atom in enumerate(self.atoms):
                if atom.atno > maxaw:
                    mm = i
        return mm

    # Finds metal atoms in molecule
    #  @param self The object pointer
    #  @return List of indices of metal atoms
    def findMetal(self):
        if not self.metals:
            mm = []
            for i, atom in enumerate(self.atoms):
                if atom.ismetal():
                    mm.append(i)
            self.metals = mm
        return (self.metals)

    # Finds atoms in molecule with given symbol
    #  @param self The object pointer
    #  @param sym Desired element symbol
    #  @return List of indices of atoms with given symbol
    def findAtomsbySymbol(self, sym):
        mm = []
        for i, atom in enumerate(self.atoms):
            if atom.sym == sym:
                mm.append(i)
        return mm

    # Finds a submolecule within the molecule given the starting atom and the separating atom
    #
    #  Illustration: H2A-B-C-DH2 will return C-DH2 if C is the starting atom and B is the separating atom.
    #
    #  Alternatively, if C is the starting atom and D is the separating atom, returns H2A-B-C.
    #  @param self The object pointer
    #  @param atom0 Index of starting atom
    #  @param atomN Index of separating atom
    #  @return List of indices of atoms in submolecule
    def findsubMol(self, atom0, atomN, smart=False):
        '''
        mol: mol3D object
        atom0: starting atom index. Note that atom0 cannot be the same as atomN
        atomN: the atom index at which we break the graph.
        '''
        if atom0 == atomN:
            raise ValueError("atom0 cannot be the same as atomN!")
        subm = []
        conatoms = [atom0]
        if not smart:
            conatoms += self.getBondedAtoms(atom0)  # connected atoms to atom0
        else:
            conatoms += self.getBondedAtomsSmart(atom0)
        if atomN in conatoms:
            conatoms.remove(atomN)  # check for atomN and remove
        subm += conatoms  # add to submolecule
        # print('conatoms', conatoms)
        while len(conatoms) > 0:  # while list of atoms to check loop
            for atidx in subm:  # loop over initial connected atoms
                if atidx != atomN:  # check for separation atom
                    if not smart:
                        newcon = self.getBondedAtoms(atidx)
                    else:
                        newcon = self.getBondedAtomsSmart(atidx)
                    if atomN in newcon:
                        newcon.remove(atomN)
                    for newat in newcon:
                        if newat not in conatoms and newat not in subm:
                            conatoms.append(newat)
                            subm.append(newat)
                if atidx in conatoms:
                    conatoms.remove(atidx)  # remove from list to check
        # subm.sort()
        return subm

    # Gets an atom with specified index
    #  @param self The object pointer
    #  @param idx Index of desired atom
    #  @return atom3D of desired atom
    def getAtom(self, idx):
        return self.atoms[idx]

    def getAtomwithinds(self, inds):
        return [self.atoms[idx] for idx in inds]

    # Gets atoms in molecule
    #  @param self The object pointer
    #  @return List of atoms in molecule
    def getAtoms(self):
        return self.atoms

    # Gets number of unique elements in molecule
    #  @param self The object pointer
    #  @return List of symbols of unique elements in molecule
    def getAtomTypes(self):
        unique_atoms_list = list()
        for atoms in self.getAtoms():
            if atoms.symbol() not in unique_atoms_list:
                unique_atoms_list.append(atoms.symbol())
        return unique_atoms_list

    # Gets coordinates of atom with specified index
    #  @param self The object pointer
    #  @param idx Index of desired atom
    #  @return List of coordinates of desired atom
    def getAtomCoords(self, idx):
        # print(self.printxyz())
        return self.atoms[idx].coords()

    # Gets atoms bonded to a specific atom
    #
    #  This is determined based on BOMatrix..
    #
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @return List of indices of bonded atoms
    def getBondedAtomsBOMatrix(self, ind, debug=False):
        ratom = self.getAtom(ind)
        self.convert2OBMol()
        OBMatrix = self.populateBOMatrix()
        # calculates adjacent number of atoms
        nats = []
        for i in range(len(OBMatrix[ind])):
            if OBMatrix[ind][i] > 0:
                nats.append(i)
        return nats

    # Gets atoms bonded to a specific atom
    #
    #  This is determined based on augmented BOMatrix.
    #
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @return List of indices of bonded atoms
    def getBondedAtomsBOMatrixAug(self, ind, debug=False):
        ratom = self.getAtom(ind)
        self.convert2OBMol()
        OBMatrix = self.populateBOMatrixAug()
        # calculates adjacent number of atoms
        nats = []
        for i in range(len(OBMatrix[ind])):
            if OBMatrix[ind][i] > 0:
                nats.append(i)
        return nats

    def getBondCutoff(self, atom, ratom):
        distance_max = 1.15 * (atom.rad + ratom.rad)
        if atom.symbol() == "C" and not ratom.symbol() == "H":
            distance_max = min(2.75, distance_max)
        if ratom.symbol() == "C" and not atom.symbol() == "H":
            distance_max = min(2.75, distance_max)
        if ratom.symbol() == "H" and atom.ismetal:
            # tight cutoff for metal-H bonds
            distance_max = 1.1 * (atom.rad + ratom.rad)
        if atom.symbol() == "H" and ratom.ismetal:
            # tight cutoff for metal-H bonds
            distance_max = 1.1 * (atom.rad + ratom.rad)
        # if atom.symbol() == "I" or ratom.symbol() == "I" and not (
        #         atom.symbol() == "I" and ratom.symbol() == "I"):
        #     # Very strict cutoff for bonds involving iodine
        #     distance_max = 0.95 * (atom.rad + ratom.rad)
        # if atom.symbol() == "I" and ratom.symbol() == "I":
        #     distance_max = 3
        # print(distance_max)
        return distance_max

    # Gets atoms bonded to a specific atom
    #
    #  This is determined based on element-specific distance cutoffs, rather than predefined valences.
    #
    #  This method is ideal for metals because bond orders are ill-defined.
    #
    #  For pure organics, the OBMol class provides better functionality.
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @return List of indices of bonded atoms
    def getBondedAtoms(self, ind, debug=False):
        if len(self.graph):
            nats = list(np.nonzero(np.ravel(self.graph[ind]))[0])
        else:
            ratom = self.getAtom(ind)
            # calculates adjacent number of atoms
            nats = []
            for i, atom in enumerate(self.atoms):
                d = distance(ratom.coords(), atom.coords())
                distance_max = self.getBondCutoff(atom, ratom)
                # distance_max = 1.15 * (atom.rad + ratom.rad)
                # if atom.symbol() == "C" and not ratom.symbol() == "H":
                #    distance_max = min(2.75, distance_max)
                # if ratom.symbol() == "C" and not atom.symbol() == "H":
                #    distance_max = min(2.75, distance_max)
                # if ratom.symbol() == "H" and atom.ismetal:
                #    # tight cutoff for metal-H bonds
                #    distance_max = 1.1 * (atom.rad + ratom.rad)
                # if atom.symbol() == "H" and ratom.ismetal:
                #    # tight cutoff for metal-H bonds
                #    distance_max = 1.1 * (atom.rad + ratom.rad)
                # if atom.symbol() == "I" or ratom.symbol() == "I" and not (
                #        atom.symbol() == "I" and ratom.symbol() == "I"):
                #    distance_max = 1.05 * (atom.rad + ratom.rad)
                # if atom.symbol() == "I" and ratom.symbol() == "I":
                #    distance_max = 3
                #    # print(distance_max)
                if (d < distance_max and i != ind):
                    nats.append(i)
        return nats

    # Gets atoms bonded to a specific atom with a given threshold
    #
    #  This is determined based on user-specific distance cutoffs.
    #
    #  This method is ideal for metals because bond orders are ill-defined.
    #
    #  For pure organics, the OBMol class provides better functionality.
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @param threshold multiplier for the sum of covalent radii cut-off
    #  @return List of indices of bonded atoms
    def getBondedAtomsByThreshold(self, ind, threshold, debug=False):
        ratom = self.getAtom(ind)
        # calculates adjacent number of atoms
        nats = []
        for i, atom in enumerate(self.atoms):
            d = distance(ratom.coords(), atom.coords())
            distance_max = threshold * (atom.rad + ratom.rad)
            if atom.symbol() == "C" and not ratom.symbol() == "H":
                distance_max = min(2.75, distance_max)
            if ratom.symbol() == "C" and not atom.symbol() == "H":
                distance_max = min(2.75, distance_max)
            if ratom.symbol() == "H" and atom.ismetal:
                # tight cutoff for metal-H bonds
                distance_max = 1.1 * (atom.rad + ratom.rad)
            if atom.symbol() == "H" and ratom.ismetal:
                # tight cutoff for metal-H bonds
                distance_max = 1.1 * (atom.rad + ratom.rad)
            if atom.symbol() == "I" or ratom.symbol() == "I" and not (atom.symbol() == "I" and ratom.symbol() == "I"):
                distance_max = 1.05 * (atom.rad + ratom.rad)
                # print(distance_max)
            if atom.symbol() == "I" or ratom.symbol() == "I":
                distance_max = 0
            if (d < distance_max and i != ind):
                nats.append(i)
        return nats

    # Gets a user-specified number of atoms bonded to a specific atom
    #
    #  This is determined based on adjusting the threshold until the number of atoms specified is reached.
    #
    #  This method is ideal for metals because bond orders are ill-defined.
    #
    #  For pure organics, the OBMol class provides better functionality.
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @param CoordNo the number of atoms specified
    #  @return List of indices of bonded atoms
    def getBondedAtomsByCoordNo(self, ind, CoordNo, debug=False):
        ratom = self.getAtom(ind)
        # calculates adjacent number of atoms
        nats = []
        thresholds = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8]
        for i, threshold in enumerate(thresholds):
            nats = self.getBondedAtomsByThreshold(ind, threshold)
            if len(nats) == CoordNo:
                break
        if len(nats) != CoordNo:
            print(
                'Could not find the number of bonded atoms specified coordinated to the atom specified.')
            print(
                'Please either adjust the number of bonded atoms or the index of the center atom.')
            print('A list of bonded atoms is still returned. Be cautious with the list')

        return nats

    # Gets atoms bonded to a specific atom specialized for octahedral complexes
    #
    #  More sophisticated version of getBondedAtoms(), written by JP.
    #
    #  This method specifically forbids "intruder" C and H atoms that would otherwise be within the distance cutoff in tightly bound complexes.
    #
    #  It also limits bonding atoms to the CN closest atoms (CN = coordination number).
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @param CN Coordination number of reference atom (default 6)
    #  @param debug Debug flag (default False)
    #  @return List of indices of bonded atoms
    def getBondedAtomsOct(self, ind, CN=6, debug=False, flag_loose=False, atom_specific_cutoffs=False):
        # INPUT
        #   - ind: index of reference atom
        #   - CN: known coordination number of complex (default 6)
        # OUTPUT
        #   - nats: list of indices of connected atoms
        ratom = self.getAtom(ind)
        # print('called slow function...')
        # calculates adjacent number of atoms
        nats = []
        if len(self.graph):
            nats = list(np.nonzero(np.ravel(self.graph[ind]))[0])
        else:
            for i, atom in enumerate(self.atoms):
                valid = True  # flag
                d = distance(ratom.coords(), atom.coords())
                # default interatomic radius
                # for non-metalics
                if atom_specific_cutoffs:
                    distance_max = self.getBondCutoff(atom, ratom)
                else:
                    distance_max = 1.15 * (atom.rad + ratom.rad)
                if atom.ismetal() or ratom.ismetal():
                    # dist_allowed = {"C": 2.8, "H": 2.0, "N": 2.8, "P": 3.0, "I": 3.5, "O": 2.8}
                    # if atom.symbol() in dist_allowed.keys():
                    #    max_pos_distance = dist_allowed[atom.symbol()]
                    # elif ratom.symbol() in dist_allowed.keys():
                    #    max_pos_distance = dist_allowed[ratom.symbol()]
                    # else:
                    #    max_pos_distance = 2.9

                    # one the atoms is a metal!
                    # use a longer max for metals
                    if flag_loose:
                        distance_max = min(3.5, 1.75 * (atom.rad + ratom.rad))
                    else:
                        distance_max = 1.37 * (atom.rad + ratom.rad)
                    if debug:
                        print(('metal in  cat ' + str(atom.symbol()) +
                               ' and rat ' + str(ratom.symbol())))
                        print(('maximum bonded distance is ' + str(distance_max)))
                    if atom.symbol() == 'He' or ratom.symbol() == 'He':
                        distance_max = 1.6 * (atom.rad + ratom.rad)
                    # print("distance_max: ", distance_max, str(atom.symbol()))
                    if d < distance_max and i != ind:
                        # trim Hydrogens
                        if atom.symbol() == 'H' or ratom.symbol() == 'H':
                            if debug:
                                print('invalid due to hydrogens: ')
                                print((atom.symbol()))
                                print((ratom.symbol()))
                            valid = False  # Hydrogen catom control
                        if d < distance_max and i != ind and valid:
                            if atom.symbol() in ["C", "S", "N"]:
                                if debug:
                                    print('\n')
                                    print(('this atom in is ' + str(i)))
                                    print(
                                        ('this atom sym is ' + str(atom.symbol())))
                                    print(('this ratom in is ' +
                                           str(self.getAtom(i).symbol())))
                                    print(
                                        ('this ratom sym is ' + str(ratom.symbol())))
                                # in this case, atom might be intruder C!
                                possible_inds = self.getBondedAtomsnotH(
                                    ind)  # bonded to metal
                                if debug:
                                    print(('poss inds are' + str(possible_inds)))
                                if len(possible_inds) > CN:
                                    metal_prox = sorted(
                                        possible_inds, key=lambda x: self.getDistToMetal(x, ind))

                                    allowed_inds = metal_prox[0:CN]
                                    # if
                                    if debug:
                                        print(('ind: ' + str(ind)))
                                        print(('metal prox: ' + str(metal_prox)))
                                        print(
                                            ('trimmed to: ' + str(allowed_inds)))
                                        print(allowed_inds)
                                        print(('CN is ' + str(CN)))

                                    if not i in allowed_inds:
                                        valid = False
                                        if debug:
                                            print(
                                                ('bond rejected based on atom: ' + str(i) + ' not in ' + str(allowed_inds)))
                                    else:
                                        if debug:
                                            print('Ok based on atom')
                            if ratom.symbol() in ["C", "S", "N"]:
                                # in this case, ratom might be intruder C or S
                                possible_inds = self.getBondedAtomsnotH(
                                    i)  # bonded to metal
                                metal_prox = sorted(
                                    possible_inds, key=lambda x: self.getDistToMetal(x, i))
                                if len(possible_inds) > CN:
                                    allowed_inds = metal_prox[0:CN]
                                    if debug:
                                        print(('ind: ' + str(ind)))
                                        print(('metal prox:' + str(metal_prox)))
                                        print(
                                            ('trimmed to ' + str(allowed_inds)))
                                        print(allowed_inds)
                                    if not ind in allowed_inds:
                                        valid = False
                                        if debug:
                                            print(('bond rejected based on ratom ' + str(
                                                ind) + ' with symbol ' + ratom.symbol()))
                                    else:
                                        if debug:
                                            print('ok based on ratom...')
                    else:
                        if debug:
                            print('distance too great')
                if (d < distance_max and i != ind):
                    if valid:
                        if debug:
                            print(('Valid atom  ind ' + str(i) + ' (' + atom.symbol() + ') and ' + str(
                                ind) + ' (' + ratom.symbol() + ')'))
                            print((' at distance ' + str(d) +
                                   ' (which is less than ' + str(distance_max) + ')'))
                        nats.append(i)
                    else:
                        if debug:
                            print(('atom  ind ' + str(i) +
                                   ' (' + atom.symbol() + ')'))
                            print(('has been disallowed from bond with ' +
                                   str(ind) + ' (' + ratom.symbol() + ')'))
                            print((' at distance ' + str(d) + ' (which would normally be less than ' + str(
                                distance_max) + ')'))
                        if d < 2 and not atom.symbol() == 'H' and not ratom.symbol() == 'H':
                            print(
                                'Error, mol3D could not understand conenctivity in mol')
        return nats

    # Gets atoms bonded to a specific atom using the molecular graph, or creates it
    #
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @param oct Flag to turn on special octahedral complex routines
    #  @return List of indices of bonded atoms
    def getBondedAtomsSmart(self, ind, oct=True, geo_check=False):
        if not len(self.graph):
            self.createMolecularGraph(oct=oct)
        return list(np.nonzero(np.ravel(self.graph[ind]))[0])

    # Gets non-H atoms bonded to a specific atom
    #
    #  Otherwise identical to getBondedAtoms().
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @return List of indices of bonded atoms
    def getBondedAtomsnotH(self, ind, metal_multiplier=1.35, nonmetal_multiplier=1.15):
        ratom = self.getAtom(ind)
        # calculates adjacent number of atoms
        nats = []
        for i, atom in enumerate(self.atoms):
            d = distance(ratom.coords(), atom.coords())
            # distance_max = 1.15 * (atom.rad + ratom.rad)
            if atom.ismetal() or ratom.ismetal():
                distance_max = metal_multiplier * (atom.rad + ratom.rad)
            else:
                distance_max = nonmetal_multiplier * (atom.rad + ratom.rad)
            if (d < distance_max and i != ind and atom.sym != 'H'):
                nats.append(i)
        return nats

    # Gets H atoms bonded to a specific atom
    #
    #  Otherwise identical to getBondedAtoms().
    #  @param self The object pointer
    #  @param ind Index of reference atom
    #  @return List of indices of bonded atoms
    def getBondedAtomsH(self, ind):
        ratom = self.getAtom(ind)
        # calculates adjacent number of atoms
        nats = []
        for i, atom in enumerate(self.atoms):
            d = distance(ratom.coords(), atom.coords())
            distance_max = 1.15 * (atom.rad + ratom.rad)
            if atom.ismetal() or ratom.ismetal():
                distance_max = 1.35 * (atom.rad + ratom.rad)
            else:
                distance_max = 1.15 * (atom.rad + ratom.rad)
            if (d < distance_max and i != ind and atom.sym == 'H'):
                nats.append(i)
        return nats

    # Gets C=C atoms in molecule
    #  @param self The object pointer
    #  @return List of atom3D objects of H atoms
    def getC2Cs(self):
        # values to store
        c2clist = []
        c2list = []
        # self.createMolecularGraph(oct=False)
        # order c2 carbons by priority
        # c2list_and_prio = []
        # for i in range(self.natoms):
        #     if self.getAtom(i).sym == 'C' and len(self.getBondedAtoms(i)) == 3:
        #         fatnos = sorted([self.getAtom(fidx).atno for fidx in self.getBondedAtoms(i)])[::-1]
        #         fpriority = float('.'.join([str(fatnos[0]), ''.join([str(i) for i in fatnos[1:]])]))
        #         c2list_and_prio.append((fpriority, i))
        # c2 carbons
        for i in range(self.natoms):
            if self.getAtom(i).sym == 'C' and len(self.getBondedAtoms(i)) == 3:
                c2list.append(i)
        # c2list = [c2[0] for c2 in sorted(c2list_and_prio)[::-1]]
        # for each c2 carbon, find if any of its neighbors are c2
        for c2 in c2list:
            fidxes = self.getBondedAtoms(c2)
            c2partners = []
            for fidx in fidxes:
                if fidx in c2list:
                    # c2partners.append(fidx)
                    c2clist.append([c2, fidx])
                    c2clist.append([fidx, c2])
            # num_c2partners = len(c2partners)
            # # if num_c2partners > 1:
            # #     for c2partner in c2partners:
            # #         score = 0
            # #         sidxes = self.getBondedAtoms(fidx)
            # #         for sidx in sidxes:
            # # elif num_c2partners == 1:
            # if num_c2partners > 1:
            #     c2clist.append([c2, fidx],[fidx, c2])
            #     continue
            # else:
            #     continue

        return c2clist

    # Gets atom that is furthest from the molecule COM along a given direction and returns the corresponding distance
    #  @param self The object pointer
    #  @param uP Search direction
    #  @return Distance
    def getfarAtomdir(self, uP):
        dd = 1000.0
        atomc = [0.0, 0.0, 0.0]
        for atom in self.atoms:
            d0 = distance(atom.coords(), uP)
            if d0 < dd:
                dd = d0
                atomc = atom.coords()
        return distance(self.centermass(), atomc)

    # Gets atom that is furthest from the given atom
    #  @param self The object pointer
    #  @param reference index of reference atom
    #  @param symbol type of atom to return
    #  @return farIndex index of furthest atom

    def getFarAtom(self, reference, atomtype=False):
        referenceCoords = self.getAtom(reference).coords()
        dd = 0.00
        farIndex = reference
        for ind, atom in enumerate(self.atoms):
            allow = False
            if atomtype:
                if atom.sym == atomtype:
                    allow = True
                else:
                    allow = False

            else:
                allow = True
            d0 = distance(atom.coords(), referenceCoords)
            if d0 > dd and allow:
                dd = d0
                farIndex = ind
        return farIndex

    # Gets list of atoms of the fragments in the mol3D
    #  @param sel The object pointer
    def getfragmentlists(self):
        atidxes_total = []
        atidxes_unique = set([0])
        atidxes_done = []
        natoms_total_ = len(atidxes_done)
        natoms_total = self.natoms
        while natoms_total_ < natoms_total:
            natoms_ = len(atidxes_unique)
            for atidx in atidxes_unique:
                if atidx not in atidxes_done:
                    atidxes_done.append(atidx)
                    atidxes = self.getBondedAtoms(atidx)
                    atidxes.extend(atidxes_unique)
                    atidxes_unique = set(atidxes)
                    natoms = len(atidxes_unique)
                    natoms_total_ = len(atidxes_done)
            if natoms_ == natoms:
                atidxes_total.append(list(atidxes_unique))
                for atidx in range(natoms_total):
                    if atidx not in atidxes_done:
                        atidxes_unique = set([atidx])
                        natoms_total_ = len(atidxes_done)
                        break

        return atidxes_total

    # Gets H atoms in molecule
    #  @param self The object pointer
    #  @return List of atom3D objects of H atoms
    def getHs(self):
        hlist = []
        for i in range(self.natoms):
            if self.getAtom(i).sym == 'H':
                hlist.append(i)
        return hlist

    # Gets H atoms bonded to specific atom3D in molecule
    #  @param self The object pointer
    #  @param ratom atom3D of reference atom
    #  @return List of atom3D objects of H atoms
    def getHsbyAtom(self, ratom):
        nHs = []
        for i, atom in enumerate(self.atoms):
            if atom.sym == 'H':
                d = distance(ratom.coords(), atom.coords())
                if (d < 1.2 * (atom.rad + ratom.rad) and d > 0.01):
                    nHs.append(i)
        return nHs

    # Gets H atoms bonded to specific atom index in molecule
    #
    #  Trivially equivalent to getHsbyAtom().
    #  @param self The object pointer
    #  @param idx Index of reference atom
    #  @return List of atom3D objects of H atoms
    def getHsbyIndex(self, idx):
        # calculates adjacent number of hydrogens
        nHs = []
        for i, atom in enumerate(self.atoms):
            if atom.sym == 'H':
                d = distance(atom.coords(), self.getAtom(idx).coords())
                if (d < 1.2 * (atom.rad + self.getAtom(idx).rad) and d > 0.01):
                    nHs.append(i)
        return nHs

    # Gets index of closest atom to reference atom.
    #  @param self The object pointer
    #  @param atom0 Index of reference atom
    #  @return Index of closest atom
    def getClosestAtom(self, atom0):
        # INPUT
        #   - atom0: reference atom3D
        # OUTPUT
        #   - idx: index of closest atom to atom0 from molecule
        idx = 0
        cdist = 1000
        for iat, atom in enumerate(self.atoms):
            ds = atom.distance(atom0)
            if (ds < cdist):
                idx = iat
                cdist = ds
        return idx

    def getClosestAtomlist(self, atom_idx, cdist=3):
        # INPUT
        #   - atom_index: reference atom index
        #   - cdist: cutoff of neighbor distance
        # OUTPUT
        #   - neighbor_list: index of close atom to atom0 from molecule
        neighbor_list = []
        for iat, atom in enumerate(self.atoms):
            ds = atom.distance(self.atoms[atom_idx])
            if (ds < cdist):
                neighbor_list.append(neighbor_list)
        return neighbor_list

    # Gets point that corresponds to mask
    #  @param self The object pointer
    #  @param mask Identifier for atoms
    #  @return Center of mass of mask
    def getMask(self, mask):
        globs = globalvars()
        elements = globs.elementsbynum()
        # check center of mass
        ats = []
        # loop over entries in mask
        for entry in mask:
            # check for center of mass
            if ('com' in entry.lower()) or ('cm' in entry.lower()):
                return self.centermass()
            # check for range
            elif '-' in entry:
                at0 = entry.split('-')[0]
                at1 = entry.split('-')[-1]
                for i in range(int(at0), int(at1) + 1):
                    ats.append(i - 1)  # python indexing
            elif entry in elements:
                ats += self.findAtomsbySymbol(entry)
            else:
                # try to convert to integer
                try:
                    t = int(entry)
                    ats.append(t - 1)
                except:
                    return self.centermass()
        maux = mol3D()
        for at in ats:
            maux.addAtom(self.getAtom(at))
        if maux.natoms == 0:
            return self.centermass()
        else:
            return maux.centermass()

    # Gets index of closest non-H atom to another atom
    #  @param self The object pointer
    #  @param atom0 atom3D of reference atom
    #  @return Index of closest non-H atom
    def getClosestAtomnoHs(self, atom0):
        idx = 0
        cdist = 1000
        for iat, atom in enumerate(self.atoms):
            ds = atom.distance(atom0)
            if (ds < cdist) and atom.sym != 'H':
                idx = iat
                cdist = ds
        return idx

    # Gets distance between two atoms in molecule
    #  @param self The object pointer
    #  @param idx Index of first atom
    #  @param metalx Index of second atom
    #  @return Distance between atoms
    def getDistToMetal(self, idx, metalx):
        d = self.getAtom(idx).distance(self.getAtom(metalx))
        return d

    # Gets angle between atoms in molecule
    #  @param self The object pointer
    #  @param idx0 Index of first atom
    #  @param idx1 Index of second (middle)
    #  @param idx2 Index of third atom
    #  @return angle between vectors formed by atom0->atom1 and atom2->atom1
    def getAngle(self, idx0, idx1, idx2):
        coords0 = self.getAtomCoords(idx0)
        coords1 = self.getAtomCoords(idx1)
        coords2 = self.getAtomCoords(idx2)
        v1 = (np.array(coords0) - np.array(coords1)).tolist()
        v2 = (np.array(coords2) - np.array(coords1)).tolist()
        angle = vecangle(v1, v2)
        return angle

    # Gets index of closest non-H atom to another atom
    #
    #  Equivalent to getClosestAtomnoHs() except that the index of the reference atom is specified.
    #  @param self The object pointer
    #  @param atidx Index of reference atom
    #  @return Index of closest non-H atom

    def getClosestAtomnoHs2(self, atidx):
        idx = 0
        cdist = 1000
        for iat, atom in enumerate(self.atoms):
            ds = atom.distance(self.getAtom(atidx))
            if (ds < cdist) and atom.sym != 'H' and iat != atidx:
                idx = iat
                cdist = ds
        return idx

    # Initializes OBMol object from a file or SMILES string

    #
    #  Uses the obConversion tool and for files containing 3D coordinates (xyz,mol) and the OBBuilder tool otherwise (smiles).
    #  @param self The object pointer
    #  @param fst Name of input file
    #  @param convtype Input filetype (xyz,mol,smi)
    #  @param ffclean Flag for FF cleanup of generated structure (default False)
    #  @return OBMol object
    def getOBMol(self, fst, convtype, ffclean=False):
        obConversion = openbabel.OBConversion()
        OBMol = openbabel.OBMol()
        if convtype == 'smistring':
            obConversion.SetInFormat('smi')
            obConversion.ReadString(OBMol, fst)
        else:
            obConversion.SetInFormat(convtype[:-1])
            obConversion.ReadFile(OBMol, fst)
        if 'smi' in convtype:
            OBMol.AddHydrogens()
            b = openbabel.OBBuilder()
            b.Build(OBMol)
        if ffclean:
            forcefield = openbabel.OBForceField.FindForceField('mmff94')
            forcefield.Setup(OBMol)
            forcefield.ConjugateGradients(200)
            forcefield.GetCoordinates(OBMol)
        self.OBMol = OBMol
        return OBMol

    # Removes attributes from mol3D object
    #  @param self The object pointer
    def initialize(self):
        self.atoms = []
        self.natoms = 0
        self.mass = 0
        self.size = 0
        self.graph = []

    # Calculates the largest distance between atoms of two molecules
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @return Largest distance between atoms in both molecules
    def maxdist(self, mol):
        # INPUT
        #   - mol: second molecule
        # OUTPUT
        #   - maxd: maximum distance between atoms of the 2 molecules
        maxd = 0
        for atom1 in mol.atoms:
            for atom0 in self.atoms:
                if (distance(atom1.coords(), atom0.coords()) > maxd):
                    maxd = distance(atom1.coords(), atom0.coords())
        return maxd

    # Calculates the smallest distance between atoms of two molecules
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @return Smallest distance between atoms in both molecules
    def mindist(self, mol):
        # INPUT
        #   - mol: second molecule
        # OUTPUT
        #   - mind: minimum distance between atoms of the 2 molecules
        mind = 1000
        for atom1 in mol.atoms:
            for atom0 in self.atoms:
                if (distance(atom1.coords(), atom0.coords()) < mind):
                    mind = distance(atom1.coords(), atom0.coords())
        return mind

    # Calculates the smallest distance between atoms in the molecule
    #  @param self The object pointer
    #  @return Smallest distance between atoms in molecule
    def mindistmol(self):
        mind = 1000
        for ii, atom1 in enumerate(self.atoms):
            for jj, atom0 in enumerate(self.atoms):
                d = distance(atom1.coords(), atom0.coords())
                if (d < mind) and ii != jj:
                    mind = distance(atom1.coords(), atom0.coords())
        return mind

    # Calculates the smallest distance from atoms in the molecule to a given point
    #  @param self The object pointer
    #  @param point List of coordinates of reference point
    #  @return Smallest distance to point
    def mindisttopoint(self, point):
        mind = 1000
        for atom1 in self.atoms:
            d = distance(atom1.coords(), point)
            if (d < mind):
                mind = d
        return mind

    # Calculates the smallest distance between non-H atoms of two molecules
    #
    #  Otherwise equivalent to mindist().
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @return Smallest distance between non-H atoms in both molecules
    def mindistnonH(self, mol):
        mind = 1000
        for atom1 in mol.atoms:
            for atom0 in self.atoms:
                if (distance(atom1.coords(), atom0.coords()) < mind):
                    if (atom1.sym != 'H' and atom0.sym != 'H'):
                        mind = distance(atom1.coords(), atom0.coords())
        return mind

    # Calculates the size of the molecule, as quantified by the max. distance between atoms and the COM.
    #  @param self The object pointer
    #  @return Molecule size (max. distance between atoms and COM)
    def molsize(self):
        maxd = 0
        cm = self.centermass()
        for atom in self.atoms:
            if distance(cm, atom.coords()) > maxd:
                maxd = distance(cm, atom.coords())
        return maxd

    # Checks for overlap with another molecule
    #
    #  Compares pairwise atom distances to 0.85*sum of covalent radii
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @param silence Flag for printing warnings
    #  @return Flag for overlap
    def overlapcheck(self, mol, silence):
        overlap = False
        for atom1 in mol.atoms:
            for atom0 in self.atoms:
                if (distance(atom1.coords(), atom0.coords()) < 0.85 * (atom1.rad + atom0.rad)):
                    overlap = True
                    if not (silence):
                        print()
                        "#############################################################"
                        print()
                        "!!!Molecules might be overlapping. Increase distance!!!"
                        print()
                        "#############################################################"
                    break
        return overlap

    # Checks for overlap with another molecule with increased tolerance
    #
    #  Compares pairwise atom distances to 1*sum of covalent radii
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @return Flag for overlap
    def overlapcheckh(self, mol):
        overlap = False
        for atom1 in mol.atoms:
            for atom0 in self.atoms:
                if (distance(atom1.coords(), atom0.coords()) < 1.0):
                    overlap = True
                    break
        return overlap

    # Gets a matrix with bond orders from openbabel
    #  @param self The object pointer
    #  @param bonddict Flag for if the obmol bond dictionary should be saved
    #  @return matrix of bond orders
    def populateBOMatrix(self, bonddict=False):
        obiter = openbabel.OBMolBondIter(self.OBMol)
        n = self.natoms
        molBOMat = np.zeros((n, n))
        bond_dict = dict()
        for bond in obiter:
            these_inds = [bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()]
            this_order = bond.GetBondOrder()
            molBOMat[these_inds[0] - 1, these_inds[1] - 1] = this_order
            molBOMat[these_inds[1] - 1, these_inds[0] - 1] = this_order
            bond_dict[tuple(
                sorted([these_inds[0]-1, these_inds[1]-1]))] = this_order
        if not bonddict:
            return (molBOMat)
        else:
            self.bo_dict = bond_dict
            return (molBOMat)

    # Gets a matrix with bond orders from openbabel augmented with molecular graph
    #  @param self The object pointer
    #  @return matrix of bond orders
    def populateBOMatrixAug(self):
        obiter = openbabel.OBMolBondIter(self.OBMol)
        n = self.natoms
        molBOMat = np.zeros((n, n))
        for bond in obiter:
            these_inds = [bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()]
            this_order = bond.GetBondOrder()
            molBOMat[these_inds[0] - 1, these_inds[1] - 1] = this_order
            molBOMat[these_inds[1] - 1, these_inds[0] - 1] = this_order
        self.convert2mol3D()
        self.createMolecularGraph()
        molgraph = self.graph
        error_mat = molBOMat - molgraph
        error_idx = np.where(error_mat < 0)
        for i in range(len(error_idx)):
            if len(error_idx[i]) > 0:
                molBOMat[error_idx[i].tolist()[0], error_idx[i].tolist()[1]] = 1
        return (molBOMat)

    # Prints xyz coordinates to stdout
    #
    #  To write to file (more common), use writexyz() instead.
    #  @param self The object pointer
    def printxyz(self):
        for atom in self.atoms:
            xyz = atom.coords()
            ss = "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])

            print(ss)

    # returns string of xyz coordinates
    #
    #  To write to file (more common), use writexyz() instead.
    #  @param self The object pointer
    def returnxyz(self):
        ss = ''
        for atom in self.atoms:
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])
        return (ss)

    # Load molecule from xyz file
    #
    #  Consider using getOBMol, which is more general, instead.
    #  @param self The object pointer
    #  @param filename Filename
    def readfromxyz(self, filename):
        # print('!!!!', filename)
        globs = globalvars()
        amassdict = globs.amass()
        self.graph = []
        self.xyzfile = filename
        fname = filename.split('.xyz')[0]
        f = open(fname + '.xyz', 'r')
        s = f.read().splitlines()
        f.close()
        for line in s[2:]:
            line_split = line.split()
            if len(line_split) == 4 and line_split[0]:
                # this looks for unique atom IDs in files
                lm = re.search(r'\d+$', line_split[0])
                # if the string ends in digits m will be a Match object, or None otherwise.
                if lm is not None:
                    symb = re.sub('\d+', '', line_split[0])
                    number = lm.group()
                    # print('sym and number ' +str(symb) + ' ' + str(number))
                    globs = globalvars()
                    atom = atom3D(symb, [float(line_split[1]), float(line_split[2]), float(line_split[3])],
                                  name=line_split[0])
                elif line_split[0] in list(amassdict.keys()):
                    atom = atom3D(line_split[0], [float(line_split[1]), float(
                        line_split[2]), float(line_split[3])])
                else:
                    print('cannot find atom type')
                    sys.exit()
                self.addAtom(atom)

    # Load molecule from mol2 file
    # Now accounts for bond orders as well as atom types (SYBYL)
    # @param self The object pointer
    # @param filename The name of the mol2file or string being read in
    # @param readstring Whether a string of mol2 file is being passed as the filename
    def readfrommol2(self, filename, readstring=False):
        # print('!!!!', filename)
        globs = globalvars()
        amassdict = globs.amass()
        graph = False
        bo_dict = False
        if readstring:
            s = filename.splitlines()
        else:
            with open(filename, 'r') as f:
                s = f.read().splitlines()
        read_atoms = False
        read_bonds = False
        self.charge = 0
        for line in s:
            # Get Atoms First
            if '<TRIPOS>BOND' in line:
                read_atoms = False
            if '<TRIPOS>SUBSTRUCTURE' in line:
                read_bonds = False
            if read_atoms:
                s_line = line.split()
                # Check redundancy in Chemical Symbols
                atom_symbol1 = re.sub('[0-9]+[A-Z]+', '', line.split()[1])
                atom_symbol1 = re.sub('[0-9]+', '', atom_symbol1)
                atom_symbol2 = line.split()[5]
                if len(atom_symbol2.split('.')) > 1:
                    atype = atom_symbol2.split('.')[1]
                else:
                    atype = False
                atom_symbol2 = atom_symbol2.split('.')[0]
                if atom_symbol1 in list(amassdict.keys()):
                    atom = atom3D(atom_symbol1, [float(s_line[2]), float(
                        s_line[3]), float(s_line[4])], name=atype)
                elif atom_symbol2 in list(amassdict.keys()):
                    atom = atom3D(atom_symbol2, [float(s_line[2]), float(
                        s_line[3]), float(s_line[4])], name=atype)
                else:
                    print('Cannot find atom symbol in amassdict')
                    sys.exit()
                self.charge += float(s_line[8])
                self.partialcharges.append(float(s_line[8]))
                self.addAtom(atom)
            if '<TRIPOS>ATOM' in line:
                read_atoms = True
            if read_bonds:  # Read in bonds to molecular graph
                s_line = line.split()
                graph[int(s_line[1]) - 1, int(s_line[2]) - 1] = 1
                graph[int(s_line[2]) - 1, int(s_line[1]) - 1] = 1
                bo_dict[tuple(
                    sorted([int(s_line[1]) - 1, int(s_line[2]) - 1]))] = s_line[3]
            if '<TRIPOS>BOND' in line:
                read_bonds = True
                # initialize molecular graph
                graph = np.zeros((self.natoms, self.natoms))
                bo_dict = dict()
        if isinstance(graph, np.ndarray):  # Enforce mol2 molecular graph if it exists
            self.graph = graph
            self.bo_dict = bo_dict
        else:
            self.graph = []
            self.bo_dict = []
    # Load molecule from xyz file
    #
    #  Consider using getOBMol, which is more general, instead.
    #  @param self The object pointer
    #  @param filename Filename

    def readfromstring(self, xyzstring):
        # print('!!!!', filename)
        globs = globalvars()
        amassdict = globs.amass()
        self.graph = []
        s = xyzstring.split('\n')
        try:
            s.remove('')
        except:
            pass
        s = [str(val) + '\n' for val in s]
        for line in s[0:]:
            line_split = line.split()
            if len(line_split) == 4 and line_split[0]:
                # this looks for unique atom IDs in files
                lm = re.search(r'\d+$', line_split[0])
                # if the string ends in digits m will be a Match object, or None otherwise.
                if lm is not None:
                    symb = re.sub('\d+', '', line_split[0])
                    number = lm.group()
                    # print('sym and number ' +str(symb) + ' ' + str(number))
                    globs = globalvars()
                    atom = atom3D(symb, [float(line_split[1]), float(line_split[2]), float(line_split[3])],
                                  name=line_split[0])
                elif line_split[0] in list(amassdict.keys()):
                    atom = atom3D(line_split[0], [float(line_split[1]), float(
                        line_split[2]), float(line_split[3])])
                else:
                    print('cannot find atom type')
                    sys.exit()
                self.addAtom(atom)

    def readfromtxt(self, txt):
        # print('!!!!', filename)
        globs = globalvars()
        en_dict = globs.endict()
        self.graph = []
        for line in txt:
            line_split = line.split()
            if len(line_split) == 4 and line_split[0]:
                # this looks for unique atom IDs in files
                lm = re.search(r'\d+$', line_split[0])
                # if the string ends in digits m will be a Match object, or None otherwise.
                if lm is not None:
                    symb = re.sub('\d+', '', line_split[0])
                    # number = lm.group()
                    # # print('sym and number ' +str(symb) + ' ' + str(number))
                    # globs = globalvars()
                    atom = atom3D(symb, [float(line_split[1]), float(line_split[2]), float(line_split[3])],
                                  name=line_split[0])
                elif line_split[0] in list(en_dict.keys()):
                    atom = atom3D(line_split[0], [float(line_split[1]), float(
                        line_split[2]), float(line_split[3])])
                else:
                    print('cannot find atom type')
                    sys.exit()
                self.addAtom(atom)

    # Computes RMSD between two molecules
    #
    #  Note that this routine does not perform translations or rotations to align molecules.
    #
    #  To do so, use geometry.kabsch().
    #  @param self The object pointer
    #  @param mol2 mol3D of second molecule
    #  @return RMSD between molecules, NaN if molecules have different numbers of atoms
    def rmsd(self, mol2):
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        if (Nat0 != Nat1):
            print(
                "ERROR: RMSD can be calculated only for molecules with the same number of atoms..")
            return float('NaN')
        else:
            rmsd = 0
            for atom0, atom1 in zip(self.getAtoms(), mol2.getAtoms()):
                rmsd += (atom0.distance(atom1)) ** 2
            if Nat0 == 0:
                rmsd = 0
            else:
                rmsd /= Nat0
            return sqrt(rmsd)

    def geo_rmsd(self, mol2):
        # print("==========")
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        if Nat0 == Nat1:
            rmsd = 0
            availabel_set = list(range(Nat1))
            for ii, atom0 in enumerate(self.getAtoms()):
                dist = 1000
                ind1 = False
                atom0_sym = atom0.symbol()
                for _ind1 in availabel_set:
                    atom1 = mol2.getAtom(_ind1)
                    if atom1.symbol() == atom0_sym:
                        _dist = atom0.distance(atom1)
                        # print(atom1.symbol(), _dist)
                        if _dist < dist:
                            dist = _dist
                            ind1 = _ind1
                rmsd += dist ** 2
                # print("paired: ", ii, ind1, dist)
                availabel_set.remove(ind1)
            if Nat0 == 0:
                rmsd = 0
            else:
                rmsd /= Nat0
            return sqrt(rmsd)
        else:
            raise ValueError("Number of atom does not match between two mols.")

    # Computes mean of absolute atom deviations
    #
    #  Like above, this routine does not perform translations or rotations to align molecules.
    #
    #  Use mol3D objects that do not use hydrogens
    #
    #  To do so, use geometry.kabsch().
    #  @param self The object pointer
    #  @param mol2 mol3D of second molecule
    #  @return sum of absolute deviations of atoms between molecules, NaN if molecules have different numbers of atoms
    def meanabsdev(self, mol2):
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        if (Nat0 != Nat1):
            print(
                "ERROR: Absolute atom deviations can be calculated only for molecules with the same number of atoms..")
            return float('NaN')
        else:
            dev = 0
            for atom0, atom1 in zip(self.getAtoms(), mol2.getAtoms()):
                dev += abs((atom0.distance(atom1)))
            if Nat0 == 0:
                dev = 0
            else:
                dev /= Nat0
            return dev

    def maxatomdist(self, mol2):
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        dist_max = 0
        if (Nat0 != Nat1):
            print(
                "ERROR: max_atom_dist can be calculated only for molecules with the same number of atoms..")
            return float('NaN')
        else:
            for atom0, atom1 in zip(self.getAtoms(), mol2.getAtoms()):
                dist = atom0.distance(atom1)
                if dist > dist_max:
                    dist_max = dist
            return dist_max

    def geo_maxatomdist(self, mol2):
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        if (Nat0 != Nat1):
            print(
                "ERROR: RMSD can be calculated only for molecules with the same number of atoms..")
            return float('NaN')
        else:
            maxdist = 0
            availabel_set = list(range(Nat1))
            for atom0 in self.getAtoms():
                dist = 1000
                ind1 = False
                atom0_sym = atom0.symbol()
                for _ind1 in availabel_set:
                    atom1 = mol2.getAtom(_ind1)
                    if atom1.symbol() == atom0_sym:
                        _dist = atom0.distance(atom1)
                        if _dist < dist:
                            dist = _dist
                            ind1 = _ind1
                if dist > maxdist:
                    maxdist = dist
                availabel_set.remove(ind1)
            return maxdist

    def rmsd_nonH(self, mol2):
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        if (Nat0 != Nat1):
            print(
                "ERROR: RMSD can be calculated only for molecules with the same number of atoms..")
            return float('NaN')
        else:
            rmsd = 0
            for atom0, atom1 in zip(self.getAtoms(), mol2.getAtoms()):
                if (not atom0.sym == 'H') and (not atom1.sym == 'H'):
                    rmsd += (atom0.distance(atom1)) ** 2
            rmsd /= Nat0
            return sqrt(rmsd)

    def maxatomdist_nonH(self, mol2):
        Nat0 = self.natoms
        Nat1 = mol2.natoms
        dist_max = 0
        if (Nat0 != Nat1):
            print(
                "ERROR: max_atom_dist can be calculated only for molecules with the same number of atoms..")
            return float('NaN')
        else:
            for atom0, atom1 in zip(self.getAtoms(), mol2.getAtoms()):
                if (not atom0.sym == 'H') and (not atom1.sym == 'H'):
                    dist = atom0.distance(atom1)
                    if dist > dist_max:
                        dist_max = dist
            return dist_max

    def calcCharges(self, charge=0, bond=False, method='QEq'):
        self.convert2OBMol()
        self.OBMol.SetTotalCharge(charge)
        charge = openbabel.OBChargeModel.FindType(method)
        charge.ComputeCharges(self.OBMol)
        self.partialcharges = charge.GetPartialCharges()

    # Checks for overlap within the molecule
    #
    #  Single-molecule version of overlapcheck().
    #  @param self The object pointer
    #  @param silence Flag for printing warning
    #  @return Flag for overlap
    #  @return Minimum distance between atoms
    def sanitycheck(self, silence=False, debug=False):
        overlap = False
        mind = 1000
        errors_dict = {}
        for ii, atom1 in enumerate(self.atoms):
            for jj, atom0 in enumerate(self.atoms):
                if jj > ii:
                    if atom1.ismetal() or atom0.ismetal():
                        cutoff = 0.6
                    elif (atom0.sym in ['N', 'O'] and atom1.sym == 'H') or (atom1.sym in ['N', 'O'] and atom0.sym == 'H'):
                        cutoff = 0.6
                    else:
                        cutoff = 0.65
                    if ii != jj and (distance(atom1.coords(), atom0.coords()) < cutoff * (atom1.rad + atom0.rad)):
                        overlap = True
                        norm = distance(
                            atom1.coords(), atom0.coords())/(atom1.rad+atom0.rad)
                        errors_dict.update(
                            {atom1.sym + str(ii)+'-'+atom0.sym+str(jj)+'_normdist': norm})
                        if distance(atom1.coords(), atom0.coords()) < mind:
                            mind = distance(atom1.coords(), atom0.coords())
                        if not (silence):
                            print(
                                "#############################################################")
                            print(
                                "Molecules might be overlapping. Increase distance!")
                            print(
                                "#############################################################")
        if debug:
            return overlap, mind, errors_dict
        else:
            return overlap, mind

    # Check that the molecule passes basic angle tests in line with CSD pulls

    # @param self: the object pointer
    # @param oct bool: if octahedral test
    # @param  angle1: metal angle cutoff
    # @param angle2: organics angle cutoff
    # @param angle3: metal/organic angle cutoff e.g. M-X-X angle
    # @return sane (bool: if sane octahedral molecule)
    # @return  error_dict (optional - if debug) dict: {bondidists and angles breaking constraints:values}

    def sanitycheckCSD(self, oct=False, angle1=30, angle2=80, angle3=45, debug=False, metals=None):
        import itertools
        if metals:
            metalinds = [i for i, x in enumerate(
                self.symvect()) if x in metals]
        else:
            metalinds = self.findMetal()
        mcons = []
        metal_syms = []
        if len(metalinds):  # only if there are metals
            for metal in metalinds:
                metalcons = self.getBondedAtomsSmart(metal, oct=oct)
                mcons.append(metalcons)
                metal_syms.append(self.symvect()[metal])
        overlap, _, errors_dict = self.sanitycheck(silence=True, debug=True)
        heavy_atoms = [i for i, x in enumerate(self.symvect()) if (
            x != 'H') and (x not in metal_syms)]
        sane = not overlap
        for i, metal in enumerate(metalinds):  # Check metal center angles
            if len(mcons[i]) > 1:
                combos = itertools.combinations(mcons[i], 2)
                for combo in combos:
                    if self.getAngle(combo[0], metal, combo[1]) < angle1:
                        sane = False
                        label = self.atoms[combo[0]].sym+str(combo[0]) + '-' + \
                            self.atoms[metal].sym+str(metal)+'-' + \
                            self.atoms[combo[1]].sym+str(combo[1]) + '_angle'
                        angle = self.getAngle(combo[0], metal, combo[1])
                        errors_dict.update({label: angle})
        for indx in heavy_atoms:  # Check heavy atom angles
            if len(self.getBondedAtomsSmart(indx, oct=oct)) > 1:
                combos = itertools.combinations(
                    self.getBondedAtomsSmart(indx), 2)
                for combo in combos:
                    # Any metals involved in the bond, but not the metal center
                    if any([True for x in combo if self.atoms[x].ismetal()]):
                        cutoff = angle3
                    else:  # Only organic/ligand bonds.
                        cutoff = angle2
                    if self.getAngle(combo[0], indx, combo[1]) < cutoff:
                        sane = False
                        label = self.atoms[combo[0]].sym+str(combo[0]) + '-' + \
                            self.atoms[indx].sym+str(indx)+'-' + \
                            self.atoms[combo[1]].sym+str(combo[1]) + '_angle'
                        angle = self.getAngle(combo[0], indx, combo[1])
                        errors_dict.update({label: angle})
        if debug:
            return sane, errors_dict
        else:
            return sane

    def isPristine(self, unbonded_min_dist=1.3, oct=False):
        # isPristine() checks if the organic portions of a transition metal complex look good
        # returns a tuple with 2 entries
            # 1. a boolean describing whether this complex passes (True) or fails (False)
            # 2. a list of failing criteria, described as strings
        if len(self.graph) == 0:
            self.createMolecularGraph(oct=oct)

        failure_reason = []
        pristine = True
        metal_idx = self.findMetal()
        non_metals = [i for i in range(self.natoms) if i not in metal_idx]

        # Ensure that non-bonded atoms are well-seperated (not close to overlapping or crowded)
        for atom1 in non_metals:
            bonds = self.graph[atom1]
            for atom2 in non_metals:
                if atom1 == atom2:  # ignore pairwise interactions
                    continue
                bond = bonds[atom2]
                if bond < 0.1:  # these atoms are not bonded
                    min_distance = unbonded_min_dist * \
                        (self.atoms[atom1].rad+self.atoms[atom2].rad)
                    d = distance(self.atoms[atom1].coords(),
                                 self.atoms[atom2].coords())
                    if d < min_distance:
                        failure_reason.append(
                            'Crowded organic atoms '+str(atom1)+'-'+str(atom2)+' '+str(round(d, 2))+' Angstrom')
                        pristine = False

        return pristine, failure_reason

    # Translate all atoms by given vector.
    #  @param self The object pointer
    #  @param dxyz Translation vector
    def translate(self, dxyz):
        for atom in self.atoms:
            atom.translate(dxyz)

    # Writes xyz file in GAMESS format
    #  @param self The object pointer
    #  @param filename Filename
    def writegxyz(self, filename):
        ss = ''  # initialize returning string
        ss += "Date:" + time.strftime(
            '%m/%d/%Y %H:%M') + ", XYZ structure generated by mol3D Class, " + self.globs.PROGRAM + "\nC1\n"
        for atom in self.atoms:
            xyz = atom.coords()
            ss += "%s \t%.1f\t%f\t%f\t%f\n" % (atom.sym,
                                               float(atom.atno), xyz[0], xyz[1], xyz[2])
        fname = filename.split('.gxyz')[0]
        f = open(fname + '.gxyz', 'w')
        f.write(ss)
        f.close()

    # Writes xyz file
    #
    #  To print to stdout instead, use printxyz().
    #  @param self The object pointer
    #  @param filename Filename
    def writexyz(self, filename, symbsonly=False, ignoreX=False, ordering=False):
        ss = ''  # initialize returning string
        natoms = self.natoms
        if not ordering:
            ordering = list(range(natoms))
        if ignoreX:
            natoms -= sum([1 for i in self.atoms if i.sym == "X"])

        ss += str(natoms) + "\n" + time.strftime(
            '%m/%d/%Y %H:%M') + ", XYZ structure generated by mol3D Class, " + self.globs.PROGRAM + "\n"
        for ii in ordering:
            atom = self.getAtom(ii)
            if not (ignoreX and atom.sym == 'X'):
                xyz = atom.coords()
                if symbsonly:
                    ss += "%s \t%f\t%f\t%f\n" % (atom.sym,
                                                 xyz[0], xyz[1], xyz[2])
                else:
                    ss += "%s \t%f\t%f\t%f\n" % (atom.name,
                                                 xyz[0], xyz[1], xyz[2])
        fname = filename.split('.xyz')[0]
        f = open(fname + '.xyz', 'w')
        f.write(ss)
        f.close()

    # Writes xyz file for 2 molecules combined
    #
    #  Used when placing binding molecules.
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @param filename Filename
    def writemxyz(self, mol, filename):
        ss = ''  # initialize returning string
        ss += str(self.natoms + mol.natoms) + "\n" + time.strftime(
            '%m/%d/%Y %H:%M') + ", XYZ structure generated by mol3D Class, " + self.globs.PROGRAM + "\n"
        for atom in self.atoms:
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])
        for atom in mol.atoms:
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])
        fname = filename.split('.xyz')[0]
        f = open(fname + '.xyz', 'w')
        f.write(ss)
        f.close()

    # Writes xyz file with atom numbers
    #
    #  some codes require this, e.g. packmol/moltemplate.
    #  @param self The object pointer
    #  @param filename Filename
    def writenumberedxyz(self, filename):
        ss = ''  # initialize returning string
        ss += str(self.natoms) + "\n" + time.strftime(
            '%m/%d/%Y %H:%M') + ", XYZ structure generated by mol3D Class, " + self.globs.PROGRAM + "\n"
        unique_types = dict()

        for atom in self.atoms:
            this_sym = atom.symbol()
            if not this_sym in list(unique_types.keys()):
                unique_types.update({this_sym: 1})
            else:
                unique_types.update({this_sym: unique_types[this_sym] + 1})
            atom_name = str(atom.symbol()) + str(unique_types[this_sym])
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom_name, xyz[0], xyz[1], xyz[2])
        fname = filename.split('.xyz')[0]
        f = open(fname + '.xyz', 'w')
        f.write(ss)
        f.close()

    # Writes xyz file for 2 molecules separated
    #
    #  Used when placing binding molecules for computation of binding energy.
    #  @param self The object pointer
    #  @param mol mol3D of second molecule
    #  @param filename Filename
    def writesepxyz(self, mol, filename):
        ss = ''  # initialize returning string
        ss += str(self.natoms) + "\n" + time.strftime(
            '%m/%d/%Y %H:%M') + ", XYZ structure generated by mol3D Class, " + self.globs.PROGRAM + "\n"
        for atom in self.atoms:
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])
        ss += "--\n" + str(mol.natoms) + "\n\n"
        for atom in mol.atoms:
            xyz = atom.coords()
            ss += "%s \t%f\t%f\t%f\n" % (atom.sym, xyz[0], xyz[1], xyz[2])
        fname = filename.split('.xyz')[0]
        f = open(fname + '.xyz', 'w')
        f.write(ss)
        f.close()

    # Write mol2 file from mol3D object
    # If partial charges are given they are appended
    # Otherwise the total charge of the complex (either given or OBMol) is
    # Assigned to the metal
    #  @param self The object pointer
    #  @param filename Filename
    #  @param writestring Bool to write to a string if True or file if False
    #  @param ignoreX will delete atom X
    #  @param force will dictate if bond orders are written (obmol/assigned) or =1
    def writemol2(self, filename, writestring=False, ignoreX=False, force=False):
        # print('!!!!', filename)
        from scipy.sparse import csgraph
        if ignoreX:
            for i, atom in enumerate(self.atoms):
                if atom.sym == 'X':
                    self.deleteatom(i)
        if not len(self.graph):
            self.createMolecularGraph()
        if not self.bo_dict and not force:
            self.convert2OBMol2()
        csg = csgraph.csgraph_from_dense(self.graph)
        disjoint_components = csgraph.connected_components(csg)
        if disjoint_components[0] > 1:
            atom_group_names = ['RES'+str(x+1) for x in disjoint_components[1]]
            atom_groups = [str(x+1) for x in disjoint_components[1]]
        else:
            atom_group_names = ['RES1']*self.natoms
            atom_groups = [str(1)]*self.natoms
        atom_types = list(set(self.symvect()))
        atom_type_numbers = np.ones(len(atom_types))
        atom_types_mol2 = []
        try:
            metal_ind = self.findMetal()[0]
        except:
            metal_ind = 0
        if len(self.partialcharges):
            charges = self.partialcharges
            charge_string = 'PartialCharges'
        elif self.charge:  # Assign total charge to metal
            charges = np.zeros(self.natoms)
            charges[metal_ind] = self.charge
            charge_string = 'UserTotalCharge'
        else:  # Calc total charge with OBMol, assign to metal
            if self.OBMol:
                charges = np.zeros(self.natoms)
                charges[metal_ind] = self.OBMol.GetTotalCharge()
                charge_string = 'OBmolTotalCharge'
            else:
                charges = np.zeros(self.natoms)
                charge_string = 'ZeroCharges'
        ss = '@<TRIPOS>MOLECULE\n{}\n'.format(filename)
        ss += '{}\t{}\t{}\n'.format(self.natoms,
                                    int(csg.nnz/2), disjoint_components[0])
        ss += 'SMALL\n'
        ss += charge_string + '\n' + '****\n' + 'Generated from molSimplify\n\n'
        ss += '@<TRIPOS>ATOM\n'
        atom_default_dict = {'C': '3', 'N': '3', 'O': '2', 'S': '3', 'P': '3'}
        for i, atom in enumerate(self.atoms):
            if atom.name != atom.sym:
                atom_types_mol2 = '.'+atom.name
            elif atom.sym in atom_default_dict.keys():
                atom_types_mol2 = '.' + atom_default_dict[atom.sym]
            else:
                atom_types_mol2 = ''
            type_ind = atom_types.index(atom.sym)
            atom_coords = atom.coords()
            ss += str(i+1) + ' ' + atom.sym+str(int(atom_type_numbers[type_ind])) + '\t' + \
                '{}  {}  {} '.format(atom_coords[0], atom_coords[1], atom_coords[2]) + \
                atom.sym + atom_types_mol2 + '\t' + atom_groups[i] + \
                ' '+atom_group_names[i]+' ' + str(charges[i]) + '\n'
            atom_type_numbers[type_ind] += 1
        ss += '@<TRIPOS>BOND\n'
        bonds = csg.nonzero()
        bond_count = 1
        if self.bo_dict:
            bondorders = True
        else:
            bondorders = False
        for i, b1 in enumerate(bonds[0]):
            b2 = bonds[1][i]
            if b2 > b1 and not bondorders:
                ss += str(bond_count)+' '+str(b1+1) + ' ' + str(b2+1) + ' 1\n'
                bond_count += 1
            elif b2 > b1 and bondorders:
                ss += str(bond_count)+' '+str(b1+1) + ' ' + str(b2+1) + \
                    ' {}\n'.format(self.bo_dict[(int(b1), int(b2))])
        ss += '@<TRIPOS>SUBSTRUCTURE\n'
        unique_group_names = np.unique(atom_group_names)
        for i, name in enumerate(unique_group_names):
            ss += str(i+1)+' '+name+' '+str(atom_group_names.count(name))+'\n'
        ss += '\n'
        if writestring:
            return ss
        else:
            if '.mol2' not in filename:
                if '.' not in filename:
                    filename += '.mol2'
                else:
                    filename = filename.split('.')[0]+'.mol2'
            with open(filename, 'w') as file1:
                file1.write(ss)

    def closest_H_2_metal(self, delta=0):
        min_dist_H = 3.0
        min_dist_nonH = 3.0
        for i, atom in enumerate(self.atoms):
            if atom.ismetal():
                metal_atom = atom
                break
        metal_coord = metal_atom.coords()
        for atom1 in self.atoms:
            if atom1.sym == 'H':
                if distance(atom1.coords(), metal_coord) < min_dist_H:
                    min_dist_H = distance(atom1.coords(), metal_coord)
            elif not atom1.ismetal():
                if distance(atom1.coords(), metal_coord) < min_dist_nonH:
                    min_dist_nonH = distance(atom1.coords(), metal_coord)
        if min_dist_H <= (min_dist_nonH - delta):
            flag = True
        else:
            flag = False
        return (flag, min_dist_H, min_dist_nonH)

    # Print methods
    #  @param self The object pointer
    #  @return String with methods
    def __repr__(self):
        # OUTPUT
        #   - ss: string with all methods
        # overloaded function
        """ when calls mol3D object without attribute e.g. t """
        ss = "\nClass mol3D has the following methods:\n"
        for method in dir(self):
            if callable(getattr(self, method)):
                ss += method + '\n'
        return ss

    # Initialize the geometry check dictionary according to the dict_oct_check_st.
    def geo_dict_initialization(self):
        for key in self.dict_oct_check_st[list(self.dict_oct_check_st.keys())[0]]:
            self.geo_dict[key] = -1
        self.dict_lig_distort = {'rmsd_max': -1, 'atom_dist_max': -1}
        self.dict_catoms_shape = {
            'oct_angle_devi_max': -1,
            'max_del_sig_angle': -1,
            'dist_del_eq': 0,
            'dist_del_all': -1,
            'dist_del_eq_relative': 0,
            'dist_del_all_relative': -1,
        }
        self.dict_orientation = {'devi_linear_avrg': -1, 'devi_linear_max': -1}

    # Get the coordination number of the metal from getBondedOct, a distance check.
    # num_coord_metal and the list of indexs of the connecting atoms are stored in mol3D
    def get_num_coord_metal(self, debug):
        metal_list = self.findMetal()
        metal_ind = self.findMetal()[0]
        metal_coord = self.getAtomCoords(metal_ind)
        if len(self.graph):
            catoms = self.getBondedAtomsSmart(metal_ind)
        elif len(metal_list) > 0:
            _catoms = self.getBondedAtomsOct(ind=metal_ind)
            if debug:
                print("_catoms: ", _catoms)
            dist2metal = {}
            dist2catoms = {}
            for ind in _catoms:
                tmpd = {}
                coord = self.getAtom(ind).coords()
                dist = np.linalg.norm(np.array(coord) - np.array(metal_coord))
                dist2metal.update({ind: dist})
                for _ind in _catoms:
                    _coord = self.getAtom(_ind).coords()
                    dist = np.linalg.norm(np.array(coord) - np.array(_coord))
                    tmpd.update({_ind: dist})
                dist2catoms.update({ind: tmpd})
            _catoms_set = set()
            for ind in _catoms:
                tmp = {}
                distind = np.linalg.norm(
                    np.array(self.getAtom(ind).coords()) - np.array(metal_coord))
                tmp.update({ind: distind})
                for _ind in _catoms:
                    if dist2catoms[ind][_ind] < 1.3:
                        tmp.update({_ind: dist2metal[_ind]})
                _catoms_set.add(min(list(tmp.items()), key=lambda x: x[1])[0])
            _catoms = list(_catoms_set)
            min_bond_dist = 2.0  # This need double check with Aditya/ Michael
            if len(dist2metal) > 0:
                dists = np.array(list(dist2metal.values()))
                inds = np.where(dists > min_bond_dist)[0]
                if inds.shape[0] > 0:
                    min_bond_dist = min(dists[inds])
            max_bond_dist = min_bond_dist + 1.5  # This is an adjustable param
            catoms = []
            for ind in _catoms:
                if dist2metal[ind] <= max_bond_dist:
                    catoms.append(ind)
        else:
            metal_ind = []
            metal_coord = []
            catoms = []
        if debug:
            print(('metal coordinate:', metal_coord,
                   self.getAtom(metal_ind).symbol()))
            print(('coordinations: ', catoms, len(catoms)))
        self.catoms = catoms
        self.num_coord_metal = len(catoms)
        if debug:
            print(("self.catoms: ", self.catoms))
            print(("self.num_coord_metal: ", self.num_coord_metal))

    # Get the deviation of shape of the catoms from the desired shape, which is defined in angle_ref.
    # Input: angle_ref, a reference list of list for the expected angles (A-metal-B) of each catom.
    # catoms_arr: default as None, which uses the catoms of the mol3D. User and overwrite this catoms_arr by input.
    # Output: shape_check dictionary
    def oct_comp(self, angle_ref=False, catoms_arr=None,
                 debug=False):
        if not angle_ref:
            angle_ref = self.oct_angle_ref
        from molSimplify.Scripts.oct_check_mols import loop_target_angle_arr

        metal_coord = self.getAtomCoords(self.findMetal()[0])
        catom_coord = []
        # Note that use this only when you wanna specify the metal connecting atoms.
        # This will change the attributes of mol3D.
        if not catoms_arr == None:
            self.catoms = catoms_arr
            self.num_coord_metal = len(catoms_arr)
        else:
            self.get_num_coord_metal(debug=debug)
        theta_arr, oct_dist = [], []
        # print("!!!!catoms", self.catoms, catoms_arr)
        for atom in self.catoms:
            coord = self.getAtomCoords(atom)
            catom_coord.append(coord)
        th_input_arr = []
        catoms_map = {}
        for idx1, coord1 in enumerate(catom_coord):
            # {atom_ind_in_mol: ind_in_angle_list}
            catoms_map.update({self.catoms[idx1]: idx1})
            delr1 = (np.array(coord1) - np.array(metal_coord)).tolist()
            theta_tmp = []
            for idx2, coord2 in enumerate(catom_coord):
                if idx2 != idx1:
                    delr2 = (np.array(coord2) - np.array(metal_coord)).tolist()
                    theta = vecangle(delr1, delr2)
                    theta_tmp.append(theta)
                else:
                    theta_tmp.append(-1)
            th_input_arr.append([self.catoms[idx1], theta_tmp])
        # This will help pick out 6 catoms that forms the closest shape compared to the desired structure.
        # When we have the customized catoms_arr, it will not change anything.
        # print("!!!th_input_arr", th_input_arr, len(th_input_arr))
        # print("!!!catoms_map: ", catoms_map)
        th_output_arr, sum_del_angle, catoms_arr, max_del_sig_angle = loop_target_angle_arr(
            th_input_arr, angle_ref, catoms_map)
        self.catoms = catoms_arr
        if debug:
            print(('th:', th_output_arr))
            print(('sum_del:', sum_del_angle))
            print(('catoms_arr:', catoms_arr))
            print(('catoms_type:', [self.getAtom(x).symbol()
                                    for x in catoms_arr]))
            print(('catoms_coord:', [self.getAtom(x).coords()
                                     for x in catoms_arr]))
        for idx, ele in enumerate(th_output_arr):
            theta_arr.append([catoms_arr[idx], sum_del_angle[idx], ele])
        theta_trunc_arr = theta_arr
        theta_trunc_arr_T = list(map(list, list(zip(*theta_trunc_arr))))
        oct_catoms = theta_trunc_arr_T[0]
        oct_angle_devi = theta_trunc_arr_T[1]
        oct_angle_all = theta_trunc_arr_T[2]
        if debug:
            print(('Summation of deviation angle for catoms:', oct_angle_devi))
            print(('Angle for catoms:', oct_angle_all))
        for atom in oct_catoms:
            coord = self.getAtom(atom).coords()
            dist = np.linalg.norm(np.array(coord) - np.array(metal_coord))
            oct_dist.append(dist)
        oct_dist.sort()
        # if len(oct_dist) == 6:  # For Oct
        #     dist_del_arr = np.array(
        #         [oct_dist[3] - oct_dist[0], oct_dist[4] - oct_dist[1], oct_dist[5] - oct_dist[2]])
        #     min_posi = np.argmin(dist_del_arr)
        #     if min_posi == 0:
        #         dist_eq, dist_ax = oct_dist[:4], oct_dist[4:]
        #     elif min_posi == 1:
        #         dist_eq, dist_ax = oct_dist[1:5], [oct_dist[0], oct_dist[5]]
        #     else:
        #         dist_eq, dist_ax = oct_dist[2:], oct_dist[:2]
        #     dist_del_eq = max(dist_eq) - min(dist_eq)
        # elif len(oct_dist) == 5:  # For one empty site
        #     if (oct_dist[3] - oct_dist[0]) > (oct_dist[4] - oct_dist[1]):
        #         # ax dist is smaller
        #         dist_ax, dist_eq = oct_dist[:1], oct_dist[1:]
        #     else:
        #         # eq dist is smaller
        #         dist_ax, dist_eq = oct_dist[4:], oct_dist[:4]
        #     dist_del_eq = max(dist_eq) - min(dist_eq)
        # else:
        #     dist_eq, dist_ax = -1, -1
        #     dist_del_eq = -1
        dist_del_all = oct_dist[-1] - oct_dist[0]
        oct_dist_relative = [(np.linalg.norm(np.array(self.getAtom(ii).coords()) -
                                             np.array(metal_coord)))/(self.globs.amass()[self.getAtom(ii).sym][2]
                                                                      + self.globs.amass()[self.getAtom(self.findMetal()[0]).sym][2])
                             for ii in oct_catoms]
        dict_catoms_shape = dict()
        dict_catoms_shape['oct_angle_devi_max'] = float(max(oct_angle_devi))
        dict_catoms_shape['max_del_sig_angle'] = float(max_del_sig_angle)
        dict_catoms_shape['dist_del_eq'] = 0
        dict_catoms_shape['dist_del_all'] = float(dist_del_all)
        dict_catoms_shape['dist_del_all_relative'] = np.max(
            oct_dist_relative) - np.min(oct_dist_relative)
        dict_catoms_shape['dist_del_eq_relative'] = 0
        self.dict_catoms_shape = dict_catoms_shape
        return dict_catoms_shape, catoms_arr

    # Match the ligands of mol and init_mol by calling ligand_breakdown
    # Input: init_mol: a mol3D object of the initial geometry
    # flag_loose and BondedOct: default as False. Only used in Oct_inspection, not in geo_check.
    # flag_lbd: Whether to apply ligand_breakdown for the optimized geometry. If False, we assume the
    # indexing of the initial and optimized xyz file is the same.
    # depth: The bond depth in obtaining the truncated mol.
    # Output: liglist_shifted, liglist_init: list of list for each ligands, with one-to-one correspandance between
    # initial and optimized mol.
    # flag_match: A flag about whether the ligands of initial and optimized mol are exactly the same.
    def match_lig_list(self, init_mol, catoms_arr=None,
                       flag_loose=False, BondedOct=False,
                       flag_lbd=True, debug=False, depth=3,
                       check_whole=False, angle_ref=False):
        from molSimplify.Informatics.graph_analyze import obtain_truncation_metal
        from molSimplify.Classes.ligand import ligand_breakdown  # , ligand_assign
        flag_match = True
        self.my_mol_trunc = mol3D()
        self.my_mol_trunc.copymol3D(self)
        self.init_mol_trunc = init_mol
        if flag_lbd:  # Also do ligand breakdown for opt geo
            if not check_whole:
                # Truncate ligands at 4 bonds away from metal to aviod rotational group.
                self.my_mol_trunc = obtain_truncation_metal(self, hops=depth)
                self.init_mol_trunc = obtain_truncation_metal(
                    init_mol, hops=depth)
                self.my_mol_trunc.createMolecularGraph()
                self.init_mol_trunc.createMolecularGraph()
                self.my_mol_trunc.writexyz("final_trunc.xyz")
                self.init_mol_trunc.writexyz("init_trunc.xyz")
            liglist_init, ligdents_init, ligcons_init = ligand_breakdown(
                self.init_mol_trunc)
            liglist, ligdents, ligcons = ligand_breakdown(self.my_mol_trunc)
            liglist_atom = [[self.my_mol_trunc.getAtom(x).symbol() for x in ele]
                            for ele in liglist]
            liglist_init_atom = [[self.init_mol_trunc.getAtom(x).symbol() for x in ele]
                                 for ele in liglist_init]
            if debug:
                print(('init_mol_trunc:', [x.symbol()
                                           for x in self.init_mol_trunc.getAtoms()]))
                print(('liglist_init, ligdents_init, ligcons_init',
                       liglist_init, ligdents_init, ligcons_init))
                print(('liglist, ligdents, ligcons', liglist, ligdents, ligcons))
        else:  # ceate/use the liglist, ligdents, ligcons of initial geo as we just wanna track them down
            if debug:
                print('Just inherit the ligand list from init structure.')
            liglist_init, ligdents_init, ligcons_init = ligand_breakdown(init_mol,
                                                                         flag_loose=flag_loose,
                                                                         BondedOct=BondedOct)
            liglist, ligdents, ligcons = liglist_init[:
                                                      ], ligdents_init[:], ligcons_init[:]
            liglist_atom = [[self.getAtom(x).symbol() for x in ele]
                            for ele in liglist]
            liglist_init_atom = [[init_mol.getAtom(x).symbol() for x in ele]
                                 for ele in liglist_init]
        if not catoms_arr == None:
            catoms, catoms_init = catoms_arr, catoms_arr
        else:
            self.my_mol_trunc.writexyz("final_trunc.xyz")
            self.init_mol_trunc.writexyz("init_trunc.xyz")
            _, catoms = self.my_mol_trunc.oct_comp(
                debug=False, angle_ref=angle_ref)
            _, catoms_init = self.init_mol_trunc.oct_comp(
                debug=False, angle_ref=angle_ref)
        if debug:
            print(('ligand_list opt in symbols:', liglist_atom))
            print(('ligand_list init in symbols: ', liglist_init_atom))
            print(("catoms opt: ", catoms, [
                  self.getAtom(x).symbol() for x in catoms]))
            print(("catoms init: ", catoms_init, [
                  self.getAtom(x).symbol() for x in catoms_init]))
            print(("catoms diff: ", set(catoms) - set(catoms_init),
                   len(set(catoms) - set(catoms_init))))
        liglist_shifted = []
        if not len(set(catoms) - set(catoms_init)):
            for ii, ele in enumerate(liglist_init_atom):
                liginds_init = liglist_init[ii]
                try:
                    # if True:
                    _flag = False
                    for idx, _ele in enumerate(liglist_atom):
                        if set(ele) == set(_ele) and len(ele) == len(_ele):
                            liginds = liglist[idx]
                            if not catoms_arr == None:
                                match = True
                            else:
                                match = connectivity_match(liginds_init, liginds, self.init_mol_trunc,
                                                           self.my_mol_trunc)
                            if debug:
                                print(
                                    ('fragment in liglist_init', ele, liginds_init))
                                print(('fragment in liglist', _ele, liginds))
                                print(("match status: ", match))
                            if match:
                                posi = idx
                                _flag = True
                                break
                    liglist_shifted.append(liglist[posi])
                    liglist_atom.pop(posi)
                    liglist.pop(posi)
                    if not _flag:
                        if debug:
                            print("here1")
                            print('Ligands cannot match!')
                        flag_match = False
                except:
                    # else:
                    print("here2")
                    print('Ligands cannot match!')
                    flag_match = False
        else:
            print('Ligands cannot match! (Connecting atoms are different)')
            flag_match = False
        if debug:
            print(('returning: ', liglist_shifted, liglist_init))
        if not catoms_arr == None:  # Force as matching in inspection mode.
            flag_match = True
        return liglist_shifted, liglist_init, flag_match

    # Get the ligand distortion by comparing each individule ligands in init_mol and opt_mol.
    # Input: init_mol: a mol3D object of the initial geometry
    # flag_loose and BondedOct: default as False. Only used in Oct_inspection, not in geo_check.
    # flag_deleteH: whether to delete the hydrogen atoms in ligands comparison.
    # flag_lbd: Whether to apply ligand_breakdown for the optimized geometry. If False, we assume the
    # indexing of the initial and optimized xyz file is the same.
    # depth: The bond depth in obtaining the truncated mol.
    # Output: dict_lig_distort: rmsd_max and atom_dist_max
    def ligand_comp_org(self, init_mol, catoms_arr=None,
                        flag_deleteH=True, flag_loose=False,
                        flag_lbd=True, debug=False, depth=3,
                        BondedOct=False, angle_ref=False):
        from molSimplify.Scripts.oct_check_mols import readfromtxt
        _, _, flag_match = self.match_lig_list(init_mol,
                                               catoms_arr=catoms_arr,
                                               flag_loose=flag_loose,
                                               BondedOct=BondedOct,
                                               flag_lbd=flag_lbd,
                                               debug=debug,
                                               depth=depth,
                                               check_whole=True,
                                               angle_ref=angle_ref)
        liglist, liglist_init, _ = self.match_lig_list(init_mol,
                                                       catoms_arr=catoms_arr,
                                                       flag_loose=flag_loose,
                                                       BondedOct=BondedOct,
                                                       flag_lbd=flag_lbd,
                                                       debug=debug,
                                                       depth=depth,
                                                       check_whole=False,
                                                       angle_ref=angle_ref)
        if debug:
            print(('lig_list:', liglist, len(liglist)))
            print(('lig_list_init:', liglist_init, len(liglist_init)))
        if flag_lbd:
            mymol_xyz = self.my_mol_trunc
            initmol_xyz = self.init_mol_trunc
        else:
            mymol_xyz = self
            initmol_xyz = init_mol
        if flag_match:
            rmsd_arr, max_atom_dist_arr = [], []
            for idx, lig in enumerate(liglist):
                lig_init = liglist_init[idx]
                if debug:
                    print(('----This is %d th piece of ligand.' % (idx + 1)))
                    print(('ligand is:', lig, lig_init))
                foo = []
                for ii, atom in enumerate(mymol_xyz.atoms):
                    if ii in lig:
                        xyz = atom.coords()
                        line = '%s \t%f\t%f\t%f\n' % (
                            atom.sym, xyz[0], xyz[1], xyz[2])
                        foo.append(line)
                tmp_mol = mol3D()
                tmp_mol = readfromtxt(tmp_mol, foo)
                foo = []
                for ii, atom in enumerate(initmol_xyz.atoms):
                    if ii in lig_init:
                        xyz = atom.coords()
                        line = '%s \t%f\t%f\t%f\n' % (
                            atom.sym, xyz[0], xyz[1], xyz[2])
                        foo.append(line)
                tmp_org_mol = mol3D()
                tmp_org_mol = readfromtxt(tmp_org_mol, foo)
                if debug:
                    print(('# atoms: %d, init: %d' %
                           (tmp_mol.natoms, tmp_org_mol.natoms)))
                    print(('!!!!atoms:', [x.symbol() for x in tmp_mol.getAtoms()],
                           [x.symbol() for x in tmp_org_mol.getAtoms()]))
                if flag_deleteH:
                    tmp_mol.deleteHs()
                    tmp_org_mol.deleteHs()
                try:
                    rmsd = rigorous_rmsd(tmp_mol, tmp_org_mol,
                                         rotation="kabsch", reorder="hungarian")
                except np.linalg.LinAlgError:
                    rmsd = 0
                rmsd_arr.append(rmsd)
                atom_dist_max = -1
                max_atom_dist_arr.append(atom_dist_max)
                if debug:
                    print(('rmsd:', rmsd))
                    # print(('atom_dist_max', atom_dist_max))
            rmsd_max = max(rmsd_arr)
            atom_dist_max = max(max_atom_dist_arr)
        else:
            rmsd_max, atom_dist_max = 'lig_mismatch', 'lig_mismatch'
        try:
            dict_lig_distort = {'rmsd_max': float(
                rmsd_max), 'atom_dist_max': float(atom_dist_max)}
        except:
            dict_lig_distort = {'rmsd_max': rmsd_max,
                                'atom_dist_max': atom_dist_max}
        self.dict_lig_distort = dict_lig_distort
        return dict_lig_distort

    def find_the_other_ind(self, arr, ind):
        arr.pop(arr.index(ind))
        return arr[0]

    # To check whether a ligand is linear:
    # The input ind should be one of the connecting atoms for the metal.
    def is_linear_ligand(self, ind):
        catoms = self.getBondedAtomsSmart(ind)
        metal_ind = self.findMetal()[0]
        flag = False
        endcheck = False
        if not self.atoms[ind].sym == 'O':
            if metal_ind in catoms and len(catoms) == 2:
                ind_next = self.find_the_other_ind(catoms[:], metal_ind)
                _catoms = self.getBondedAtomsSmart(ind_next)
                # print("~~~~", (self.atoms[ind].sym, self.atoms[ind_next].sym))
                if (self.atoms[ind].sym, self.atoms[ind_next].sym) in list(self.globs.tribonddict().keys()):
                    dist = np.linalg.norm(
                        np.array(self.atoms[ind].coords()) - np.array(self.atoms[ind_next].coords()))
                    if dist > self.globs.tribonddict()[(self.atoms[ind].sym, self.atoms[ind_next].sym)]:
                        endcheck = True
                else:
                    endcheck = True
                if (not self.atoms[ind_next].sym == 'H') and (not endcheck):
                    if len(_catoms) == 1:
                        flag = True
                    elif len(_catoms) == 2:
                        ind_next2 = self.find_the_other_ind(_catoms[:], ind)
                        vec1 = np.array(self.getAtomCoords(ind)) - \
                            np.array(self.getAtomCoords(ind_next))
                        vec2 = np.array(self.getAtomCoords(
                            ind_next2)) - np.array(self.getAtomCoords(ind_next))
                        ang = vecangle(vec1, vec2)
                        if ang > 170:
                            flag = True
        # print(flag, catoms)
        return flag, catoms

    def get_linear_angle(self, ind):
        flag, catoms = self.is_linear_ligand(ind)
        if flag:
            vec1 = np.array(self.getAtomCoords(
                catoms[0])) - np.array(self.getAtomCoords(ind))
            vec2 = np.array(self.getAtomCoords(
                catoms[1])) - np.array(self.getAtomCoords(ind))
            ang = vecangle(vec1, vec2)
        else:
            ang = 0
        return flag, ang

    # Get the ligand orientation for those are linear.
    # Output: dict_angle_linear. For each ligand, whether they are linear or not and if it is, what the deviation from
    # 180 degree is.
    # dict_orientation: devi_linear_avrg and devi_linear_max
    def check_angle_linear(self, catoms_arr=None):
        dict_angle_linear = {}
        if not catoms_arr == None:
            pass
        else:
            catoms_arr = self.catoms
        for ind in catoms_arr:
            flag, ang = self.get_linear_angle(ind)
            dict_angle_linear[str(ind)] = [flag, float(ang)]
        dict_orientation = {}
        devi_linear_avrg, devi_linear_max = 0, 0
        count = 0
        for key in dict_angle_linear:
            [flag, ang] = dict_angle_linear[key]
            if flag:
                count += 1
                devi_linear_avrg += 180 - ang
                if (180 - ang) > devi_linear_max:
                    devi_linear_max = 180 - ang
        if count:
            devi_linear_avrg /= count
        else:
            devi_linear_avrg = 0
        dict_orientation['devi_linear_avrg'] = float(devi_linear_avrg)
        dict_orientation['devi_linear_max'] = float(devi_linear_max)
        self.dict_angle_linear = dict_angle_linear
        self.dict_orientation = dict_orientation
        return dict_angle_linear, dict_orientation

    # Process the self.geo_dict to get the flag_oct and flag_list, setting dict_check as the cutoffs.
    # Input: dict_check. The cutoffs of each geo_check metrics we have. A dictionary.
    # num_coord: Expected coordination number.
    # Output: flag_oct: good (1) or bad (0) structure.
    # flag_list: metrics that are failed from being a good geometry.
    def dict_check_processing(self, dict_check,
                              num_coord=6, debug=False, silent=False):
        self.geo_dict['num_coord_metal'] = int(self.num_coord_metal)
        self.geo_dict.update(self.dict_lig_distort)
        self.geo_dict.update(self.dict_catoms_shape)
        self.geo_dict.update(self.dict_orientation)
        banned_sign = 'banned_by_user'
        if debug:
            print(('dict_oct_info', self.geo_dict))
        for ele in self.std_not_use:
            self.geo_dict[ele] = banned_sign
        self.geo_dict['atom_dist_max'] = banned_sign
        flag_list = []
        for key, values in list(dict_check.items()):
            if isinstance(self.geo_dict[key], (int, float)):
                if self.geo_dict[key] > values:
                    flag_list.append(key)
            elif not self.geo_dict[key] == banned_sign:
                flag_list.append(key)
        if self.geo_dict['num_coord_metal'] < num_coord:
            flag_list.append('num_coord_metal')
        if flag_list == ['num_coord_metal'] and \
                (self.geo_dict['num_coord_metal'] == -1 or self.geo_dict['num_coord_metal'] > num_coord):
            self.geo_dict['num_coord_metal'] = num_coord
            flag_list.remove('num_coord_metal')
        if not len(flag_list):
            flag_oct = 1  # good structure
            flag_list = 'None'
        else:
            flag_oct = 0
            flag_list = '; '.join(flag_list)
            if not silent:
                print('------bad structure!-----')
                print(('flag_list:', flag_list))
        self.flag_oct = flag_oct
        self.flag_list = flag_list
        return flag_oct, flag_list, self.geo_dict

    # Print the geo_dict after the check.
    def print_geo_dict(self):
        print('========Geo_check_results========')
        print('--------coordination_check-----')
        print(('num_coord_metal:', self.num_coord_metal))
        print(('catoms_arr:', self.catoms))
        print('-------catoms_shape_check-----')
        _dict = self.dict_catoms_shape
        self.print_dict(_dict)
        print('-------individual_ligand_distortion_check----')
        _dict = self.dict_lig_distort
        self.print_dict(_dict)
        print('-------linear_ligand_orientation_check-----')
        _dict = self.dict_orientation
        self.print_dict(_dict)
        print('=======End of printing geo_check_results========')

    def print_dict(self, _dict):
        for key, value in list(_dict.items()):
            print(('%s: ' % key, value))

    # Final geometry check call for octahedral structures.
    # Input: init_mol. mol3D object for the inital geometry.
    # dict_check, The cutoffs of each geo_check metrics we have. A dictionary.
    # angle_ref, a reference list of list for the expected angles (A-metal-B) of each catom.
    # flag_catoms: whether or not to return the catoms arr. Default as False. True for the Oct_inspection
    # catoms_arr: default as None, which uses the catoms of the mol3D. User and overwrite this catoms_arr by input.
    # Output: flag_oct: good (1) or bad (0) structure.
    # flag_list: metrics that are failed from being a good geometry.
    # dict_oct_info: self.geo_dict
    def IsOct(self, init_mol=None, dict_check=False,
              angle_ref=False, flag_catoms=False,
              catoms_arr=None, debug=False,
              flag_loose=True, flag_lbd=True, BondedOct=True,
              skip=False, flag_deleteH=True,
              silent=False, use_atom_specific_cutoffs=True):
        self.use_atom_specific_cutoffs = True
        if not dict_check:
            dict_check = self.dict_oct_check_st
        if not angle_ref:
            angle_ref = self.oct_angle_ref
        if not skip:
            skip = list()
        else:
            print("Warning: your are skipping following geometry checks:")
            print(skip)
        self.get_num_coord_metal(debug=debug)
        # Note that use this only when you wanna specify the metal connecting atoms.
        # This will change the attributes of mol3D.
        if not catoms_arr == None:
            self.catoms = catoms_arr
            self.num_coord_metal = len(catoms_arr)
        if not init_mol == None:
            init_mol.get_num_coord_metal(debug=debug)
            catoms_init = init_mol.catoms
        else:
            catoms_init = [0, 0, 0, 0, 0, 0]
        self.geo_dict_initialization()
        if len(catoms_init) >= 6:
            if self.num_coord_metal >= 6:
                # if not rmsd_max == 'lig_mismatch':
                if True:
                    self.num_coord_metal = 6
                    if not 'FCS' in skip:
                        dict_catoms_shape, catoms_arr = self.oct_comp(angle_ref,
                                                                      catoms_arr,
                                                                      debug=debug,
                                                                      )
                if not init_mol == None:
                    init_mol.use_atom_specific_cutoffs = True
                    if any(self.getAtom(ii).symbol() != init_mol.getAtom(ii).symbol() for ii in range(min(self.natoms, init_mol.natoms))):
                        print(
                            "The ordering of atoms in the initial and final geometry is different.")
                        init_mol = mol3D()
                        init_mol.copymol3D(self)
                    if not 'lig_distort' in skip:
                        dict_lig_distort = self.ligand_comp_org(init_mol=init_mol,
                                                                flag_loose=flag_loose,
                                                                flag_lbd=flag_lbd,
                                                                debug=debug,
                                                                BondedOct=BondedOct,
                                                                flag_deleteH=flag_deleteH,
                                                                angle_ref=angle_ref,)
                if not 'lig_linear' in skip:
                    dict_angle_linear, dict_orientation = self.check_angle_linear()
                if debug:
                    self.print_geo_dict()
            eqsym, maxdent, ligdents, homoleptic, ligsymmetry, eq_catoms = self.get_symmetry_denticity(
                return_eq_catoms=True)
            if eqsym:
                metal_coord = self.getAtomCoords(self.findMetal()[0])
                eq_dists = [np.linalg.norm(np.array(self.getAtom(
                    ii).coords()) - np.array(metal_coord)) for ii in eq_catoms]
                eq_dists.sort()
                self.dict_catoms_shape['dist_del_eq'] = eq_dists[-1] - eq_dists[0]
                eq_dists_relative = [(np.linalg.norm(np.array(self.getAtom(ii).coords()) -
                                                     np.array(metal_coord)))/(self.globs.amass()[self.getAtom(ii).sym][2]
                                                                              + self.globs.amass()[self.getAtom(self.findMetal()[0]).sym][2])
                                     for ii in eq_catoms]
                self.dict_catoms_shape['dist_del_eq_relative'] = np.max(
                    eq_dists_relative) - np.min(eq_dists_relative)
            if not maxdent > 1:
                choice = 'mono'
            else:
                choice = 'multi'
            used_geo_cutoffs = dict_check[choice]
            if not eqsym:
                used_geo_cutoffs['dist_del_eq'] = used_geo_cutoffs['dist_del_all']
            flag_oct, flag_list, dict_oct_info = self.dict_check_processing(used_geo_cutoffs,
                                                                            num_coord=6,
                                                                            debug=debug,
                                                                            silent=silent)
        else:
            flag_oct = 0
            flag_list = ["bad_init_geo"]
            dict_oct_info = {"num_coord_metal": "bad_init_geo"}
        if not flag_catoms:
            return flag_oct, flag_list, dict_oct_info
        else:
            return flag_oct, flag_list, dict_oct_info, catoms_arr

    # Final geometry check call for customerized structures. Once we have the custumed dict_check and angle_ref.
    # Currently support one-site-empty octahedral.
    # Inputs and outputs are the same as IsOct.
    def IsStructure(self, init_mol=None, dict_check=False,
                    angle_ref=False, num_coord=5,
                    flag_catoms=False, catoms_arr=None, debug=False,
                    skip=False, flag_deleteH=True):
        self.use_atom_specific_cutoffs = True
        if not dict_check:
            dict_check = self.dict_oneempty_check_st
        if not angle_ref:
            angle_ref = self.oneempty_angle_ref
        if not skip:
            skip = list()
        else:
            print("Warning: your are skipping following geometry checks:")
            print(skip)
        self.get_num_coord_metal(debug=debug)
        if not catoms_arr == None:
            self.catoms = catoms_arr
            self.num_coord_metal = len(catoms_arr)
        if not init_mol == None:
            init_mol.get_num_coord_metal(debug=debug)
            catoms_init = init_mol.catoms
        else:
            catoms_init = [0 for i in range(num_coord)]
        self.geo_dict_initialization()
        print(angle_ref)
        if len(catoms_init) >= num_coord:
            if self.num_coord_metal >= num_coord:
                if True:
                    self.num_coord_metal = num_coord
                    if not 'FCS' in skip:
                        dict_catoms_shape, catoms_arr = self.oct_comp(angle_ref, catoms_arr,
                                                                      debug=debug)
                if not init_mol == None:
                    init_mol.use_atom_specific_cutoffs = True
                    if any(self.getAtom(ii).symbol() != init_mol.getAtom(ii).symbol() for ii in range(min(self.natoms, init_mol.natoms))):
                        print(
                            "The ordering of atoms in the initial and final geometry is different.")
                        init_mol = mol3D()
                        init_mol.copymol3D(self)
                    if not 'lig_distort' in skip:
                        dict_lig_distort = self.ligand_comp_org(
                            init_mol, flag_deleteH=flag_deleteH, debug=debug, angle_ref=angle_ref)
                if not 'lig_linear' in skip:
                    dict_angle_linear, dict_orientation = self.check_angle_linear()
                if debug:
                    self.print_geo_dict()
            eqsym, maxdent, ligdents, homoleptic, ligsymmetry, eq_catoms = self.get_symmetry_denticity(
                return_eq_catoms=True)
            if eqsym:
                metal_coord = self.getAtomCoords(self.findMetal()[0])
                eq_dists = [np.linalg.norm(np.array(self.getAtom(
                    ii).coords()) - np.array(metal_coord)) for ii in eq_catoms]
                eq_dists.sort()
                self.dict_catoms_shape['dist_del_eq'] = eq_dists[-1] - eq_dists[0]
                eq_dists_relative = [(np.linalg.norm(np.array(self.getAtom(ii).coords()) -
                                                     np.array(metal_coord)))/(self.globs.amass()[self.getAtom(ii).sym][2]
                                                                              + self.globs.amass()[self.getAtom(self.findMetal()[0]).sym][2])
                                     for ii in eq_catoms]
                self.dict_catoms_shape['dist_del_eq_relative'] = np.max(
                    eq_dists_relative) - np.min(eq_dists_relative)
            if not maxdent > 1:
                choice = 'mono'
            else:
                choice = 'multi'
            used_geo_cutoffs = dict_check[choice]
            if not eqsym:
                used_geo_cutoffs['dist_del_eq'] = used_geo_cutoffs['dist_del_all']
            flag_oct, flag_list, dict_oct_info = self.dict_check_processing(used_geo_cutoffs,
                                                                            num_coord=num_coord,
                                                                            debug=debug)
        else:
            flag_oct = 0
            flag_list = ["bad_init_geo"]
            dict_oct_info = {"num_coord_metal": "bad_init_geo"}
        if not flag_catoms:
            return flag_oct, flag_list, dict_oct_info
        else:
            return flag_oct, flag_list, dict_oct_info, catoms_arr

    # Used to track down the changing geo_check metrics in a DFT geometry optimization.
    # With the catoms_arr always specified.
    def Oct_inspection(self, init_mol=None, catoms_arr=None, dict_check=False,
                       std_not_use=[], angle_ref=False, flag_loose=True, flag_lbd=False,
                       dict_check_loose=False, BondedOct=True, debug=False):
        self.use_atom_specific_cutoffs = True
        if not dict_check:
            dict_check = self.dict_oct_check_st
        if not angle_ref:
            angle_ref = self.oct_angle_ref
        if not dict_check_loose:
            dict_check_loose = self.dict_oct_check_loose

        if catoms_arr == None:
            init_mol.get_num_coord_metal(debug=debug)
            catoms_arr = init_mol.catoms
            if len(catoms_arr) > 6:
                _, catoms_arr = init_mol.oct_comp(debug=debug)
        if len(catoms_arr) != 6:
            print('Error, must have 6 connecting atoms for octahedral.')
            print('Please DO CHECK what happens!!!!')
            flag_oct = 0
            flag_list = ["num_coord_metal"]
            dict_oct_info = {'num_coord_metal': len(catoms_arr)}
            geo_metrics = ['rmsd_max', 'atom_dist_max', 'oct_angle_devi_max', 'max_del_sig_angle',
                           'dist_del_eq', 'dist_del_all', 'devi_linear_avrg', 'devi_linear_max']
            for metric in geo_metrics:
                dict_oct_info.update({metric: "NA"})
            flag_oct_loose = 0
            flag_list_loose = ["num_coord_metal"]
        else:
            self.num_coord_metal = 6
            self.geo_dict_initialization()
            if not init_mol == None:
                init_mol.use_atom_specific_cutoffs = True
                if any(self.getAtom(ii).symbol() != init_mol.getAtom(ii).symbol() for ii in range(min(self.natoms, init_mol.natoms))):
                    raise ValueError(
                        "initial and current geometry does not match in atom ordering!")
                dict_lig_distort = self.ligand_comp_org(init_mol=init_mol,
                                                        flag_loose=flag_loose,
                                                        flag_lbd=flag_lbd,
                                                        catoms_arr=catoms_arr,
                                                        debug=debug,
                                                        BondedOct=BondedOct,
                                                        angle_ref=angle_ref)
            if not dict_lig_distort['rmsd_max'] == 'lig_mismatch':
                dict_catoms_shape, catoms_arr = self.oct_comp(angle_ref, catoms_arr,
                                                              debug=debug)
            else:
                print("Warning: Potential issues about lig_mismatch.")

            dict_angle_linear, dict_orientation = self.check_angle_linear(
                catoms_arr=catoms_arr)
            if debug:
                self.print_geo_dict()
            eqsym, maxdent, ligdents, homoleptic, ligsymmetry = self.get_symmetry_denticity()
            if not maxdent > 1:
                choice = 'mono'
            else:
                choice = 'multi'
            used_geo_cutoffs = dict_check[choice]
            if not eqsym:
                used_geo_cutoffs['dist_del_eq'] = used_geo_cutoffs['dist_del_all']
            flag_oct, flag_list, dict_oct_info = self.dict_check_processing(dict_check=used_geo_cutoffs,
                                                                            num_coord=6, debug=debug)
            flag_oct_loose, flag_list_loose, __ = self.dict_check_processing(dict_check=dict_check_loose[choice],
                                                                             num_coord=6, debug=debug)
        return flag_oct, flag_list, dict_oct_info, flag_oct_loose, flag_list_loose

    # Used to track down the changing geo_check metrics in a DFT geometry optimization.
    # With the catoms_arr always specified.
    def Structure_inspection(self, init_mol=None, catoms_arr=None, num_coord=5, dict_check=False,
                             std_not_use=[], angle_ref=False, flag_loose=True, flag_lbd=False,
                             dict_check_loose=False, BondedOct=True, debug=False):
        if not dict_check:
            dict_check = self.dict_oneempty_check_st
        if not angle_ref:
            angle_ref = self.oneempty_angle_ref
        if not dict_check_loose:
            dict_check_loose = self.dict_oneempty_check_loose

        if catoms_arr == None:
            init_mol.get_num_coord_metal(debug=debug)
            catoms_arr = init_mol.catoms
            if len(catoms_arr) > num_coord:
                _, catoms_arr = init_mol.oct_comp(
                    angle_ref=angle_ref, debug=debug)
        # print("connecting atoms are,", catoms_arr)
        if len(catoms_arr) != num_coord:
            print(('Error, must have %d connecting atoms for octahedral.' % num_coord))
            print('Please DO CHECK what happens!!!!')
            flag_oct = 0
            flag_list = ["num_coord_metal"]
            dict_oct_info = {'num_coord_metal': len(catoms_arr)}
            geo_metrics = ['rmsd_max', 'atom_dist_max', 'oct_angle_devi_max', 'max_del_sig_angle',
                           'dist_del_eq', 'dist_del_all', 'devi_linear_avrg', 'devi_linear_max']
            for metric in geo_metrics:
                dict_oct_info.update({metric: "NA"})
            flag_oct_loose = 0
            flag_list_loose = ["num_coord_metal"]
        else:
            self.num_coord_metal = num_coord
            self.geo_dict_initialization()
            if not init_mol == None:
                init_mol.use_atom_specific_cutoffs = True
                if any(self.getAtom(ii).symbol() != init_mol.getAtom(ii).symbol() for ii in range(min(self.natoms, init_mol.natoms))):
                    raise ValueError(
                        "initial and current geometry does not match in atom ordering!")
                dict_lig_distort = self.ligand_comp_org(init_mol=init_mol,
                                                        flag_loose=flag_loose,
                                                        flag_lbd=flag_lbd,
                                                        catoms_arr=catoms_arr,
                                                        debug=debug,
                                                        BondedOct=BondedOct,
                                                        angle_ref=angle_ref)
            if not dict_lig_distort['rmsd_max'] == 'lig_mismatch':
                dict_catoms_shape, catoms_arr = self.oct_comp(angle_ref, catoms_arr,
                                                              debug=debug)
            else:
                self.num_coord_metal = -1
                print('!!!!!Should always match. WRONG!!!!!')
            dict_angle_linear, dict_orientation = self.check_angle_linear(
                catoms_arr=catoms_arr)
            if debug:
                self.print_geo_dict()
            eqsym, maxdent, ligdents, homoleptic, ligsymmetry = self.get_symmetry_denticity()
            if not maxdent > 1:
                choice = 'mono'
            else:
                choice = 'multi'
            used_geo_cutoffs = dict_check[choice]
            if not eqsym:
                used_geo_cutoffs['dist_del_eq'] = used_geo_cutoffs['dist_del_all']
            flag_oct, flag_list, dict_oct_info = self.dict_check_processing(dict_check=used_geo_cutoffs,
                                                                            num_coord=num_coord, debug=debug)
            flag_oct_loose, flag_list_loose, __ = self.dict_check_processing(dict_check=dict_check_loose[choice],
                                                                             num_coord=num_coord, debug=debug)
        return flag_oct, flag_list, dict_oct_info, flag_oct_loose, flag_list_loose

    def get_fcs(self):
        metalind = self.findMetal()[0]
        self.get_num_coord_metal(debug=False)
        catoms = self.catoms
        # print(catoms, [self.getAtom(x).symbol() for x in catoms])
        if len(catoms) > 6:
            _, catoms = self.oct_comp(debug=False)
        fcs = [metalind] + catoms
        return fcs

    # Recreate bo_dict with correct indicies
    # @param self The object pointer
    # @param inds The indicies of the selected submolecule to SAVE
    # @return new_bo_dict The ported over dictionary with new indicies/bonds deleted
    def get_bo_dict_from_inds(self, inds):
        if not self.bo_dict:
            self.convert2OBMol2()
        c_bo_dict = self.bo_dict.copy()
        delete_inds = np.array(
            [x for x in range(self.natoms) if x not in inds])
        for key in self.bo_dict.keys():
            if any([True for x in key if x in delete_inds]):
                del c_bo_dict[key]
        new_bo_dict = dict()
        for key, val in c_bo_dict.items():
            ind1 = key[0]
            ind2 = key[1]
            ind1 = ind1 - len(np.where(delete_inds < ind1)[0])
            ind2 = ind2 - len(np.where(delete_inds < ind2)[0])
            new_bo_dict[(ind1, ind2)] = val
        return new_bo_dict

    def create_mol_with_inds(self, inds):
        molnew = mol3D()
        inds = sorted(inds)
        for ind in inds:
            atom = atom3D(self.atoms[ind].symbol(
            ), self.atoms[ind].coords(), self.atoms[ind].name)
            molnew.addAtom(atom)
        if self.bo_dict:
            save_bo_dict = self.get_bo_dict_from_inds(inds)
            molnew.bo_dict = save_bo_dict
        if len(self.graph):
            delete_inds = [x for x in range(self.natoms) if x not in inds]
            molnew.graph = np.delete(
                np.delete(self.graph, delete_inds, 0), delete_inds, 1)
        return molnew

    # Writes a psueduo-chemical formula
    #
    #  @param self The object pointer
    def make_formula(self, latex=True):
        retstr = ""
        atomorder = self.globs.elementsbynum()
        unique_symbols = dict()
        for atoms in self.getAtoms():
            if atoms.symbol() in atomorder:
                if not atoms.symbol() in list(unique_symbols.keys()):
                    unique_symbols[atoms.symbol()] = 1
                else:
                    unique_symbols[atoms.symbol(
                    )] = unique_symbols[atoms.symbol()] + 1
        skeys = sorted(list(unique_symbols.keys()), key=lambda x: (
            self.globs.elementsbynum().index(x)))
        skeys = skeys[::-1]
        for sk in skeys:
            if latex:
                retstr += '\\textrm{' + sk + '}_{' + \
                          str(int(unique_symbols[sk])) + '}'
            else:
                retstr += sk+str(int(unique_symbols[sk]))
        return retstr

    def read_smiles(self, smiles, ff="mmff94", steps=2500):
        # used to convert from one formst (ex, SMILES) to another (ex, mol3D )
        obConversion = openbabel.OBConversion()

        # the input format "SMILES"; Reads the SMILES - all stacked as 2-D - one on top of the other
        obConversion.SetInFormat("SMILES")
        OBMol = openbabel.OBMol()
        obConversion.ReadString(OBMol, smiles)

        # Adds Hydrogens
        OBMol.AddHydrogens()

        # Get a 3-D structure with H's
        builder = openbabel.OBBuilder()
        builder.Build(OBMol)

        # Force field optimization is done in the specified number of "steps" using the specified "ff" force field
        forcefield = openbabel.OBForceField.FindForceField(ff)
        s = forcefield.Setup(OBMol)
        if s == False:
            print('FF setup failed')
        forcefield.ConjugateGradients(steps)
        forcefield.GetCoordinates(OBMol)

        # mol3D structure
        self.OBMol = OBMol
        self.convert2mol3D()

    def get_smiles(self, canoncalize=False, use_mol2=False):
        # Used to get the SMILES string of a given mol3D object
        conv = openbabel.OBConversion()
        conv.SetOutFormat('smi')
        if canoncalize:
            conv.SetOutFormat('can')
        if self.OBMol == False:
            if use_mol2:
                # Produces a smiles with the enforced BO matrix,
                # which is needed for correct behavior for fingerprints
                self.convert2OBMol2(ignoreX=True)
            else:
                self.convert2OBMol()
        smi = conv.WriteString(self.OBMol).split()[0]
        return smi

    def mols_symbols(self):
        self.symbols_dict = {}
        for atom in self.getAtoms():
            if not atom.symbol() in self.symbols_dict:
                self.symbols_dict.update({atom.symbol(): 1})
            else:
                self.symbols_dict[atom.symbol()] += 1

    def read_bonder_order(self, bofile):
        globs = globalvars()
        bonds_organic = {'H': 1, 'C': 4, 'N': 3,
                         'O': 2, 'F': 1, 'P': 3, 'S': 2}
        self.bv_dict = {}
        self.ve_dict = {}
        self.bvd_dict = {}
        self.bodstd_dict = {}
        self.bodavrg_dict = {}
        self.bo_mat = np.zeros(shape=(self.natoms, self.natoms))
        if os.path.isfile(bofile):
            with open(bofile, "r") as fo:
                for line in fo:
                    ll = line.split()
                    if len(ll) == 5 and ll[0].isdigit() and ll[1].isdigit():
                        self.bo_mat[int(ll[0]), int(ll[1])] = float(ll[2])
                        self.bo_mat[int(ll[1]), int(ll[0])] = float(ll[2])
                        if int(ll[0]) == int(ll[1]):
                            self.bv_dict.update({int(ll[0]): float(ll[2])})
        else:
            print(("bofile does not exist.", bofile))
        for ii in range(self.natoms):
            # self.ve_dict.update({ii: globs.amass()[self.atoms[ii].symbol()][3]})
            self.ve_dict.update({ii: bonds_organic[self.atoms[ii].symbol()]})
            self.bvd_dict.update({ii: self.bv_dict[ii] - self.ve_dict[ii]})
            # neighbors = self.getBondedAtomsSmart(ii, oct=oct)
            # vec = self.bo_mat[ii, :][neighbors]
            vec = self.bo_mat[ii, :][self.bo_mat[ii, :] > 0.1]
            if vec.shape[0] == 0:
                self.bodstd_dict.update({ii: 0})
                self.bodavrg_dict.update({ii: 0})
            else:
                devi = [abs(v - max(round(v), 1)) for v in vec]
                self.bodstd_dict.update({ii: np.std(devi)})
                self.bodavrg_dict.update({ii: np.mean(devi)})

    def read_charge(self, chargefile):
        self.charge_dict = {}
        if os.path.isfile(chargefile):
            with open(chargefile, "r") as fo:
                for line in fo:
                    ll = line.split()
                    if len(ll) == 3 and ll[0].isdigit():
                        self.charge_dict.update({int(ll[0]) - 1: float(ll[2])})
        else:
            print(("chargefile does not exist.", chargefile))

    def get_mol_graph_det(self, oct=True, useBOMat=False):
        globs = globalvars()
        amassdict = globs.amass()
        if not len(self.graph):
            self.createMolecularGraph(oct=oct)
        if useBOMat:
            if (isinstance(self.BO_mat, bool)) and (isinstance(self.bo_dict, bool)):
                raise AssertionError('This mol does not have BO information.')
            elif isinstance(self.bo_dict, dict):
                # BO_dict will be prioritized over BO_mat
                tmpgraph = np.copy(self.graph)
                for key_val, value in self.bo_dict.items():
                    if str(value).lower() == 'ar':
                        value = 1.5
                    elif str(value).lower() == 'am':
                        value = 1.5
                    elif str(value).lower() == 'un':
                        value = 4
                    else:
                        value = int(value)
                    # This assigns the bond order in the BO dict
                    # to the graph, then the determinant can be taken
                    # for that graph
                    tmpgraph[key_val[0], key_val[1]] = value
                    tmpgraph[key_val[1], key_val[0]] = value
            else:
                tmpgraph = np.copy(self.BO_mat)
        else:
            tmpgraph = np.copy(self.graph)
        syms = self.symvect()
        weights = [amassdict[x][0] for x in syms]
        # Add hydrogen tolerance???
        inds = np.nonzero(tmpgraph)
        for j in range(len(syms)):
            tmpgraph[j, j] = weights[j]
        for i, x in enumerate(inds[0]):
            y = inds[1][i]
            tmpgraph[x, y] = weights[x]*weights[y]*tmpgraph[x, y]
        with np.errstate(over='raise'):
            try:
                det = np.linalg.det(tmpgraph)
            except:
                (sign, det) = np.linalg.slogdet(tmpgraph)
                if sign != 0:
                    det = sign*det
        if 'e+' in str(det):
            safedet = str(det).split(
                'e+')[0][0:12]+'e+'+str(det).split('e+')[1]
        else:
            safedet = str(det)[0:12]
        return safedet

    def get_symmetry_denticity(self, return_eq_catoms=False):
        # self.writexyz("test.xyz")
        from molSimplify.Classes.ligand import ligand_breakdown, ligand_assign_consistent, get_lig_symmetry
        liglist, ligdents, ligcons = ligand_breakdown(self)
        try:
            _, _, _, _, _, _, _, eq_con_list, _ = ligand_assign_consistent(
                self, liglist, ligdents, ligcons)
            if len(eq_con_list):
                flat_eq_ligcons = [
                    x for sublist in eq_con_list for x in sublist]
                assigned = True
            else:
                assigned = False
        except:
            assigned = False
        if ligdents:
            maxdent = max(ligdents)
        else:
            maxdent = 0
        eqsym = None
        homoleptic = True
        ligsymmetry = None
        if assigned:
            metal_ind = self.findMetal()[0]
            n_eq_syms = len(
                list(set([self.getAtom(x).sym for x in flat_eq_ligcons])))
            flat_eq_dists = [np.round(self.getDistToMetal(
                x, metal_ind), 6) for x in flat_eq_ligcons]
            minmax_eq_plane = max(flat_eq_dists) - min(flat_eq_dists)
            # Match eq plane symbols and eq plane dists
            if (n_eq_syms < 2) and (minmax_eq_plane < 0.2):
                eqsym = True
            else:
                eqsym = False
            ligsymmetry = get_lig_symmetry(self)
        if eqsym:
            for lig in liglist[1:]:
                if not connectivity_match(liglist[0], lig, self, self):
                    homoleptic = False
        else:
            homoleptic = False
        if not return_eq_catoms:
            return eqsym, maxdent, ligdents, homoleptic, ligsymmetry
        else:
            if eqsym:
                eq_catoms = flat_eq_ligcons
            else:
                eq_catoms = False
            return eqsym, maxdent, ligdents, homoleptic, ligsymmetry, eq_catoms

    def is_sandwich_compound(self):
        '''
        Check if a structure is sandwich compound.
        Request: 1) complexes with ligands where there are at least
        three connected non-metal atoms both connected to the metal.
        2) These >three connected non-metal atoms are in a ring.
        3) optional: the ring is aromatic
        4) optional: all the atoms in the base ring are connected to the same metal.
        '''
        from molSimplify.Informatics.graph_analyze import obtain_truncation_metal
        mol_fcs = obtain_truncation_metal(self, hops=1)
        metal_ind = mol_fcs.findMetal()[0]
        catoms = list(range(mol_fcs.natoms))
        catoms.remove(metal_ind)
        sandwich_ligands, _sl = list(), list()
        for atom0 in catoms:
            lig = mol_fcs.findsubMol(atom0=atom0, atomN=metal_ind, smart=True)
            # require to be at least a three-member ring
            if len(lig) >= 3 and not set(lig) in _sl:
                full_lig = self.findsubMol(atom0=mol_fcs.mapping_sub2mol[lig[0]],
                                           atomN=mol_fcs.mapping_sub2mol[metal_ind],
                                           smart=True)
                lig_inds_in_obmol = [sorted(full_lig).index(
                    mol_fcs.mapping_sub2mol[x])+1 for x in lig]
                full_ligmol = self.create_mol_with_inds(full_lig)
                full_ligmol.convert2OBMol2()
                ringlist = full_ligmol.OBMol.GetSSSR()
                for obmol_ring in ringlist:
                    if all([obmol_ring.IsInRing(x) for x in lig_inds_in_obmol]):
                        sandwich_ligands.append(
                            [set(lig), obmol_ring.Size(), obmol_ring.IsAromatic()])
                        _sl.append(set(lig))
                        break
        num_sandwich_lig = len(sandwich_ligands)
        info_sandwich_lig = [{"natoms_connected": len(
            x[0]), "natoms_ring": x[1], "aromatic": x[2]} for x in sandwich_ligands]
        aromatic = any([x["aromatic"] for x in info_sandwich_lig])
        allconnect = any([x["natoms_connected"] == x["natoms_ring"]
                          for x in info_sandwich_lig])
        return num_sandwich_lig, info_sandwich_lig, aromatic, allconnect

    def is_edge_compound(self):
        '''
        Check if a structure is edge compound.
        Request: 1) complexes with ligands where there are at least
        two connected non-metal atoms both connected to the metal.
        '''
        from molSimplify.Informatics.graph_analyze import obtain_truncation_metal
        num_sandwich_lig, info_sandwich_lig, aromatic, allconnect = self.is_sandwich_compound()
        if not num_sandwich_lig or (num_sandwich_lig and not allconnect):
            mol_fcs = obtain_truncation_metal(self, hops=1)
            metal_ind = mol_fcs.findMetal()[0]
            catoms = list(range(mol_fcs.natoms))
            catoms.remove(metal_ind)
            edge_ligands, _el = list(), list()
            for atom0 in catoms:
                lig = mol_fcs.findsubMol(
                    atom0=atom0, atomN=metal_ind, smart=True)
                if len(lig) >= 2 and not set(lig) in _el:
                    edge_ligands.append([set(lig)])
                    _el.append(set(lig))
                    break
            num_edge_lig = len(edge_ligands)
            info_edge_lig = [
                {"natoms_connected": len(x[0])} for x in edge_ligands]
        else:
            num_edge_lig, info_edge_lig = 0, list()
        return num_edge_lig, info_edge_lig

    def get_geometry_type(self, dict_check=False, angle_ref=False, num_coord=False,
                          flag_catoms=False, catoms_arr=None, debug=False,
                          skip=False):
        '''
        Get the type of the geometry (trigonal planar(3), tetrahedral(4), square planar(4),
        trigonal bipyramidal(5), square pyramidal(5, one-empty-site),
        octahedral(6), pentagonal bipyramidal(7))

        '''
        all_geometries = globalvars().get_all_geometries()
        all_angle_refs = globalvars().get_all_angle_refs()
        summary = {}
        num_sandwich_lig, info_sandwich_lig, aromatic, allconnect = False, False, False, False
        info_edge_lig, num_edge_lig = False, False
        if len(self.graph):  # Find num_coord based on metal_cn if graph is assigned
            if len(self.findMetal()) > 1:
                raise ValueError('Multimetal complexes are not yet handled.')
            elif len(self.findMetal()) == 1:
                num_coord = len(self.getBondedAtomsSmart(self.findMetal()[0]))
            else:
                raise ValueError('No metal centers exist in this complex.')
        if num_coord is not False:
            if num_coord not in [3, 4, 5, 6, 7]:
                if (catoms_arr is not None) and (not len(catoms_arr) == num_coord):
                    raise ValueError(
                        "num_coord and the length of catoms_arr do not match.")
                num_sandwich_lig, info_sandwich_lig, aromatic, allconnect = self.is_sandwich_compound()
                num_edge_lig, info_edge_lig = self.is_edge_compound()
                if num_sandwich_lig:
                    geometry = "sandwich"
                elif num_edge_lig:
                    geometry = "edge"
                else:
                    geometry = "unknown"
                results = {
                    "geometry": geometry,
                    "angle_devi": False,
                    "summary": {},
                    "num_sandwich_lig": num_sandwich_lig,
                    "info_sandwich_lig": info_sandwich_lig,
                    "aromatic": aromatic,
                    "allconnect": allconnect,
                    "num_edge_lig": num_edge_lig,
                    "info_edge_lig": info_edge_lig,
                }
                return results
            else:
                if catoms_arr is not None:
                    if not len(catoms_arr) == num_coord:
                        raise ValueError(
                            "num_coord and the length of catoms_arr do not match.")
                    num_sandwich_lig, info_sandwich_lig, aromatic, allconnect = self.is_sandwich_compound()
                    num_edge_lig, info_edge_lig = self.is_edge_compound()
                    possible_geometries = all_geometries[num_coord]
                    for geotype in possible_geometries:
                        dict_catoms_shape, _ = self.oct_comp(angle_ref=all_angle_refs[geotype],
                                                             catoms_arr=catoms_arr,
                                                             debug=debug)
                        summary.update({geotype: dict_catoms_shape})
                else:
                    num_sandwich_lig, info_sandwich_lig, aromatic, allconnect = self.is_sandwich_compound()
                    num_edge_lig, info_edge_lig = self.is_edge_compound()
                    possible_geometries = all_geometries[num_coord]
                    for geotype in possible_geometries:
                        dict_catoms_shape, catoms_assigned = self.oct_comp(angle_ref=all_angle_refs[geotype],
                                                                           catoms_arr=None,
                                                                           debug=debug)
                        if debug:
                            print("Geocheck assigned catoms: ", catoms_assigned, [
                                  self.getAtom(ind).symbol() for ind in catoms_assigned])
                        summary.update({geotype: dict_catoms_shape})
        else:
            # TODO: Implement the case where we don't know the coordination number.
            raise KeyError(
                "Not implemented yet. Please at least provide the coordination number.")
        angle_devi, geometry = 10000, False
        for geotype in summary:
            if summary[geotype]["oct_angle_devi_max"] < angle_devi:
                angle_devi = summary[geotype]["oct_angle_devi_max"]
                geometry = geotype
        if num_sandwich_lig:
            geometry = "sandwich"
            angle_devi = False
        elif num_edge_lig:
            geometry = "edge"
            angle_devi = False
        results = {
            "geometry": geometry,
            "angle_devi": angle_devi,
            "summary": summary,
            "num_sandwich_lig": num_sandwich_lig,
            "info_sandwich_lig": info_sandwich_lig,
            "aromatic": aromatic,
            "allconnect": allconnect,
            "num_edge_lig": num_edge_lig,
            "info_edge_lig": info_edge_lig,
        }
        return results
